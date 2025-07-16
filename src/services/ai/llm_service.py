"""
LLM AI 服务模块
提供与LLM API的完整交互实现，包含以下核心功能：
- API请求管理
- 上下文对话管理
- 响应安全处理
- 智能错误恢复
"""

import logging
import re
import os
import random
import json  # 新增导入
import time  # 新增导入
import pathlib
import requests
from typing import Dict, List, Optional, Tuple, Union
from openai import OpenAI
from src.autoupdate.updater import Updater
from tenacity import (
    retry,
    stop_after_attempt,
    wait_random_exponential,
    retry_if_exception_type
)

# 修改logger获取方式，确保与main模块一致
logger = logging.getLogger('main')

class LLMService:
    def __init__(self, api_key: str, base_url: str, model: str,
                 max_token: int, temperature: float, max_groups: int):
        """
        强化版AI服务初始化

        :param api_key: API认证密钥
        :param base_url: API基础URL
        :param model: 使用的模型名称
        :param max_token: 最大token限制
        :param temperature: 创造性参数(0~2)
        :param max_groups: 最大对话轮次记忆
        :param system_prompt: 系统级提示词
        """
        # 创建 Updater 实例获取版本信息
        updater = Updater()
        version = updater.get_current_version()
        version_identifier = updater.get_version_identifier()

        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            default_headers={
                "Content-Type": "application/json",
                "User-Agent": version_identifier,
                "X-KouriChat-Version": version
            }
        )
        self.config = {
            "model": model,
            "max_token": max_token,
            "temperature": temperature,
            "max_groups": max_groups,
        }

        # 上下文管理器是一个字典，里面的value再套一个list，list里面再套一个字典
        self.chat_contexts: Dict[str, List[Dict]] = {}

        # 安全字符白名单（可根据需要扩展）
        # 这个正则表达式匹配一些空白字符，隐藏空格， 控制字符等影响文本显示的字符
        self.safe_pattern = re.compile(r'[\x00-\x1F\u202E\u200B]')

        # 如果是 Ollama，获取可用模型列表
        if 'localhost:11434' in base_url:
            self.available_models = self.get_ollama_models()
        else:
            self.available_models = []

    def _manage_context(self, user_id: str, message: str, role: str = "user"):
        """
        上下文管理器（支持动态记忆窗口）

        :param user_id: 用户唯一标识
        :param message: 消息内容
        :param role: 角色类型(user/assistant)
        """

        # 给用户在上下文管理器初始化
        if user_id not in self.chat_contexts:
            self.chat_contexts[user_id] = []

        # 添加新消息
        # 给用户的字典中，用append添加了一个list元素，而list里面的元素是字典
        self.chat_contexts[user_id].append({"role": role, "content": message})

        # 维护上下文窗口
        # 看配置，最大上下文是15，这里*2 也就是超过30条消息就开始清理
        while len(self.chat_contexts[user_id]) > self.config["max_groups"] * 2:
            # 优先保留最近的对话组
            # 这里还是用了python中的 -负号 和 ：冒号来截取列表数据
            self.chat_contexts[user_id] = self.chat_contexts[user_id][-self.config["max_groups"]*2:]

    def _sanitize_response(self, raw_text: str) -> str:
        """
        响应安全处理器
        1. 移除控制字符
        2. 标准化换行符
        3. 防止字符串截断异常
        """
        try:
            # re.sub  python中，匹配正则表达式，用指定内容替换
            # raw_text原始文本，self.safe_pattern 正则表达式，'' 替换内容，
            cleaned = re.sub(self.safe_pattern, '', raw_text)
            return cleaned.replace('\r\n', '\n').replace('\r', '\n')
        except Exception as e:
            logger.error(f"Response sanitization failed: {str(e)}")
            return "响应处理异常，请重新尝试"

    def _filter_thinking_content(self, content: str) -> str:
        """
        过滤思考内容，支持不同模型的返回格式
        1. R1格式: 思考过程...\n\n\n最终回复
        2. Gemini格式: <think>思考过程</think>\n\n最终回复
        """
        try:
            # 使用分割替代正则表达式处理 Gemini 格式
            if '<think>' in content and '</think>' in content:
                parts = content.split('</think>')
                # 只保留最后一个</think>后的内容
                filtered_content = parts[-1].strip()
            else:
                filtered_content = content

            # 过滤 R1 格式 (思考过程...\n\n\n最终回复)
            # 查找三个连续换行符
            triple_newline_match = re.search(r'\n\n\n', filtered_content)
            if triple_newline_match:

                # 只保留三个连续换行符后面的内容（最终回复）
                # triple_newline_match.end() 返回的是匹配到的字符串的结束位置，
                filtered_content = filtered_content[triple_newline_match.end():]

            return filtered_content.strip()
        except Exception as e:
            logger.error(f"过滤思考内容失败: {str(e)}")
            return content  # 如果处理失败，返回原始内容

    def _validate_response(self, response: dict) -> bool:
        """
        放宽检验
        API响应校验
        只要能获取到有效的回复内容就返回True
        """
        try:
            # 调试：打印完整响应结构
            logger.debug(f"API响应结构: {json.dumps(response, default=str, indent=2)}")
            
            # 尝试获取回复内容
            # 这里验证了下响应的格式，是否和预期格式一致
            if isinstance(response, dict):
                choices = response.get("choices", [])
                if choices and isinstance(choices, list):
                    first_choice = choices[0]
                    if isinstance(first_choice, dict):
                        # 尝试不同的响应格式
                        # 格式1: choices[0].message.content
                        if isinstance(first_choice.get("message"), dict):
                            content = first_choice["message"].get("content")
                            if content and isinstance(content, str):
                                return True

                        # 格式2: choices[0].content
                        content = first_choice.get("content")
                        if content and isinstance(content, str):
                            return True

                        # 格式3: choices[0].text
                        text = first_choice.get("text")
                        if text and isinstance(text, str):
                            return True

            logger.warning("无法从响应中获取有效内容，完整响应: %s", json.dumps(response, default=str))
            return False

        except Exception as e:
            logger.error(f"验证响应时发生错误: {str(e)}")
            return False

    def get_response(self, message: str, user_id: str, system_prompt: str, previous_context: List[Dict] = None, core_memory: str = None) -> str:
        """
        完整请求处理流程
        Args:
            message: 用户消息
            user_id: 用户ID
            system_prompt: 系统提示词（人设）
            previous_context: 历史上下文（可选）
            core_memory: 核心记忆（可选）
        """
            # —— 阶段1：输入验证 ——
            if not message.strip():
                return "Error: Empty message received"

            # —— 阶段2：上下文更新 ——
            # 只在程序刚启动时（上下文为空时）加载外部历史上下文
            # 这里添加的历史上下文，就是短期记忆
            if previous_context and user_id not in self.chat_contexts:
                logger.info(f"程序启动初始化：为用户 {user_id} 加载历史上下文，共 {len(previous_context)} 条消息")
                # 确保上下文只包含当前用户的历史信息
                self.chat_contexts[user_id] = previous_context.copy()

            # 添加当前消息到上下文
            # 将当前消息添加到上下文，并且维护上下文窗口，只保留30条消息
            self._manage_context(user_id, message)

            # —— 阶段3：构建请求参数 ——
            # 读取基础Prompt
            try:
                # 从当前文件位置(llm_service.py)向上导航到项目根目录
                current_dir = os.path.dirname(os.path.abspath(__file__))  # src/services/ai
                project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))  # 项目根目录

                # 这个base文件，就像人设中的备注部分，是对大模型输出内容的一些限制
                base_prompt_path = os.path.join(project_root, "data", "base", "base.md")

                with open(base_prompt_path, "r", encoding="utf-8") as f:
                    base_content = f.read()
            except Exception as e:
                logger.error(f"基础Prompt文件读取失败: {str(e)}")
                base_content = ""

            # 构建完整提示词: base + 核心记忆 + 人设
            if core_memory:
                # system_prompt 人设，这里看到，每次请求都是携带的完整人设，也就是说，大模型每次的回答
                # 其实是当场根据人设编出来的，这样导致大模型的回答其实很肤浅，所以加入了核心记忆
                # 但这种方式其实，不是很好，大模型没有持续对话，无法模拟出真人对话的持续和流畅感
                final_prompt = f"{base_content}\n\n{core_memory}\n\n{system_prompt}"
                logger.debug("提示词顺序：base.md + 核心记忆 + 人设")
            else:
                final_prompt = f"{base_content}\n\n{system_prompt}"
                logger.debug("提示词顺序：base.md + 人设")

            # 构建消息列表
            messages = [
                {"role": "system", "content": final_prompt},

                # * 这个星号是python的解包操作，这里的get出来是一个list，里面的元素是字典，
                # 也就是[dict1，dict2，……]这样，解包之后，就变成了dict1，dict2，……
                # [-self.config["max_groups"] * 2:]  还是经典的list截取指定条记录的操作

                # 最后 messages 就是 [dict1，dict2，……] 这样的数据结构

                # 由于上面将当前用户输入的消息添加到了上下文，因此这里的messages，包含人设，核心记忆，问题等

                *self.chat_contexts.get(user_id, [])[-self.config["max_groups"] * 2:]
            ]

            # 为 Ollama 构建消息内容
            chat_history = self.chat_contexts.get(user_id, [])[-self.config["max_groups"] * 2:]
            history_text = "\n".join([

                # 这个遍历是倒过来的，先写语句，再写for
                # 最后这个字符串就是这样的，用户名:消息，用户名:消息，……
                f"{msg['role']}: {msg['content']}"
                for msg in chat_history
            ])
            ollama_message = {
                "role": "user",
                #下面三个变量分别对应  人设+核心记忆，对话历史，最新一次用户输入
                "content": f"{final_prompt}\n\n对话历史：\n{history_text}\n\n用户问题：{message}"
            }

            # 检查是否是 Ollama API
            is_ollama = 'localhost:11434' in str(self.client.base_url)
        
        # —— 阶段4：执行API请求（带重试机制）——
        max_retries = 3
        last_error = None
        
        for attempt in range(max_retries):
            try:
                filtered_content = ""

            if is_ollama:
                # Ollama API 格式
                request_config = {
                    "model": self.config["model"].split('/')[-1],  # 移除路径前缀
                    "messages": [ollama_message],  # 将消息包装在列表中
                    "stream": False,
                    "options": {
                        # temperature 大模型温度
                        "temperature": self.config["temperature"],
                        # max_tokens 大模型最大生成的token数
                        "max_tokens": self.config["max_token"]
                    }
                }

                # 使用 requests 库向 Ollama API 发送 POST 请求
                try:
                    # 创建 Updater 实例获取版本信息
                    updater = Updater()
                    version = updater.get_current_version()
                    version_identifier = updater.get_version_identifier()

                    response = requests.post(
                        f"{str(self.client.base_url)}",
                        json=request_config,
                        headers={
                            "Content-Type": "application/json",
                            "User-Agent": version_identifier,
                            "X-KouriChat-Version": version
                        }
                    )

                    # raise_for_status自动检查http响应的状态码，
                    # 当 HTTP 状态码为 200-299 时：静默通过
                    # 当状态码为 400-599 时：抛出 requests.exceptions.HTTPError 异常
                    response.raise_for_status()

                    response_data = response.json()

                    # 检查响应中是否包含 message 字段
                    if response_data and "message" in response_data:
                        raw_content = response_data["message"]["content"]

                        # 处理 R1 特殊格式，可能包含 reasoning_content 字段
                        if isinstance(response_data["message"], dict) and "reasoning_content" in response_data["message"]:
                            logger.debug("检测到 R1 格式响应，将分离思考内容")
                            # 只使用 content 字段内容，忽略 reasoning_content
                            raw_content = response_data["message"]["content"]
                    else:
                        raise ValueError(f"错误的API响应结构: {json.dumps(response_data, default=str)}")

                    # 剔除影响文本显示的内容
                    clean_content = self._sanitize_response(raw_content)

                    # 过滤思考内容
                    filtered_content = self._filter_thinking_content(clean_content)

            else:
                # 标准 OpenAI 格式
                request_config = {
                    "model": self.config["model"],  # 模型名称
                    "messages": messages,  # 消息列表
                    "temperature": self.config["temperature"],  # 温度参数
                    "max_tokens": self.config["max_token"],  # 最大 token 数
                        "top_p": 0.95,  # top_p 参数
                        "frequency_penalty": 0.2  # 频率惩罚参数
                }

                # 使用 OpenAI 客户端发送请求
                # ** 双星，专门用于解包字典，将字典中的键值对作为关键字参数传递给函数
                # 比如http需要参数model，正常可能要写  "model"：request_config["model"] 这样，
                # 但双星号就能直接给 http 赋值需要的字典参数

                # self.client初始化了一个openai的客户端，
                # .chat.completions.create 是调用openai客户端的方法
                response = self.client.chat.completions.create(**request_config)
                    
                # 验证 API 响应结构
                if not self._validate_response(response.model_dump()):
                        raise ValueError(f"错误的API响应结构: {json.dumps(response.model_dump(), default=str)}")

                # 获取原始内容
                raw_content = response.choices[0].message.content
                # 清理响应内容
                clean_content = self._sanitize_response(raw_content)
                # 过滤思考内容
                filtered_content = self._filter_thinking_content(clean_content)
                
                # 统一处理错误响应内容（以 "Error" 开头）
                if filtered_content.strip().lower().startswith("error"):
                    error_msg = filtered_content
                    logger.warning(f"检测到错误响应 (尝试 {attempt+1}/{max_retries}): {error_msg}")
                    last_error = f"错误响应: {error_msg}"
                    
                    # 如果这不是最后一次尝试，则继续下一次
                    if attempt < max_retries - 1:
                        continue
                
                # 成功获取有效响应，更新上下文并返回
                self._manage_context(user_id, filtered_content, "assistant")
                return filtered_content or ""

        except Exception as e:
                last_error = f"Error: {str(e)}"
                logger.warning(f"API请求失败 (尝试 {attempt+1}/{max_retries}): {str(e)}")
                
                # 如果这不是最后一次尝试，则继续下一次
                if attempt < max_retries - 1:
                    continue
        
        # 所有重试都失败后，记录最终错误并返回
        logger.error(f"所有重试尝试均失败: {last_error}")
        return last_error

    def clear_history(self, user_id: str) -> bool:
        """
        清空指定用户的对话历史
        """
        if user_id in self.chat_contexts:
            del self.chat_contexts[user_id]
            logger.info("已清除用户 %s 的对话历史", user_id)
            return True
        return False

    def analyze_usage(self, response: dict) -> Dict:
        """
        用量分析工具
        """
        usage = response.get("usage", {})
        return {
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "completion_tokens": usage.get("completion_tokens", 0),
            "total_tokens": usage.get("total_tokens", 0),
            "estimated_cost": (usage.get("total_tokens", 0) / 1000) * 0.02  # 示例计价
        }

    def chat(self, messages: list, **kwargs) -> str:
        """
        发送聊天请求并获取回复

        Args:
            messages: 消息列表，每个消息是包含 role 和 content 的字典
            **kwargs: 额外的参数配置

        Returns:
            str: AI的回复内容
        """
        try:
            response = self.client.chat.completions.create(
                model=self.config["model"],
                messages=messages,
                temperature=kwargs.get('temperature', self.config["temperature"]),
                max_tokens=self.config["max_token"]
            )

            if not self._validate_response(response.model_dump()):
                error_msg = f"错误的API响应结构: {json.dumps(response.model_dump(), default=str)}"
                logger.error(error_msg)
                return f"Error: {error_msg}"

            raw_content = response.choices[0].message.content
            # 清理和过滤响应内容
            clean_content = self._sanitize_response(raw_content)
            filtered_content = self._filter_thinking_content(clean_content)

            return filtered_content or ""

        except Exception as e:
            logger.error(f"Chat completion failed: {str(e)}")
            return f"Error: {str(e)}"

    def get_ollama_models(self) -> List[Dict]:
        """获取本地 Ollama 可用的模型列表"""
        try:
            response = requests.get('http://localhost:11434/api/tags')
            if response.status_code == 200:
                models = response.json().get('models', [])
                return [
                    {
                        "id": model['name'],
                        "name": model['name'],
                        "status": "active",
                        "type": "chat",
                        "context_length": 16000  # 默认上下文长度
                    }
                    for model in models
                ]
            return []
        except Exception as e:
            logger.error(f"获取Ollama模型列表失败: {str(e)}")
            return []

    def get_config(self) -> Dict:
        """
        获取当前LLM服务的配置参数
        方便外部服务（如记忆服务）获取最新配置
        
        Returns:
            Dict: 包含当前配置的字典
        """
        return self.config.copy()  # 返回配置的副本以防止外部修改