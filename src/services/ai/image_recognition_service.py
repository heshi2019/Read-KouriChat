"""
图像识别 AI 服务模块
提供与图像识别 API 的交互功能，包括:
- 图像识别
- 文本生成
- API请求处理
- 错误处理
"""

import base64
import logging
import requests
from typing import Optional
import os

# 修改logger获取方式，确保与main模块一致
logger = logging.getLogger('main')

class ImageRecognitionService:
    def __init__(self, api_key: str, base_url: str, temperature: float, model: str):
        self.api_key = api_key
        self.base_url = base_url
        # 确保 temperature 在有效范围内
        self.temperature = min(max(0.0, temperature), 1.0)  # 限制在 0-1 之间

        # 使用 Updater 获取版本信息并设置请求头
        from src.autoupdate.updater import Updater
        updater = Updater()
        version = updater.get_current_version()
        version_identifier = updater.get_version_identifier()

        self.headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',

            # 这里的请求头为什么要设置项目名称、项目版本？
            'User-Agent': version_identifier,
            'X-KouriChat-Version': version
        }

        # 这个model，是类变量，是一个
        # 卧槽了，这个变量调用真是，model变量在创建本类对象的时候传入，而model本身是config文件中，
        # 取的图箱式变model的value值
        # 在main文件中，本类被chatbox调用，chatbox调用本类时，传入了本类需要的各种值，
        # 而本类的各种值是从config文件中获取的，于是又有一个config类来操作config文件，我糙了
        self.model = model  # "moonshot-v1-8k-vision-preview"

        if temperature > 1.0:
            logger.warning(f"Temperature值 {temperature} 超出范围，已自动调整为 1.0")

    def recognize_image(self, image_path: str, is_emoji: bool = False) -> str:
        """使用 Moonshot AI 识别图片内容并返回文本"""
        try:
            # 验证图片路径
            if not os.path.exists(image_path):
                logger.error(f"图片文件不存在: {image_path}")
                return "抱歉，图片文件不存在"

            # 验证文件大小
            file_size = os.path.getsize(image_path) / (1024 * 1024)  # 转换为MB
            if file_size > 100:  # API限制为100MB
                logger.error(f"图片文件过大 ({file_size:.2f}MB): {image_path}")
                return "抱歉，图片文件太大了"

            # 读取并编码图片
            try:
                # 'rb'   二进制读取模式
                with open(image_path, 'rb') as img_file:
                    # 转为base64编码
                    image_content = base64.b64encode(img_file.read()).decode('utf-8')
            except Exception as e:
                logger.error(f"读取图片文件失败: {str(e)}")
                return "抱歉，读取图片时出现错误"

            # 设置提示词

            # 为真返回，条件判断，为假返回  这是python中的三元表达式，这怎么这么怪呢
            text_prompt = "请描述这个图片" if not is_emoji else "这是一张微信聊天的图片截图，请描述这个聊天窗口左边的聊天用户用户发送的最后一张表情，不要去识别聊天用户的头像"

            # 准备请求数据，这里是调用格式，按道理来说这个只是月之暗面的调用格式
            data = {
                "model": self.model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{image_content}"
                                }
                            },
                            {
                                "type": "text",
                                "text": text_prompt
                            }
                        ]
                    }
                ],
                "temperature": self.temperature
            }

            # 发送请求
            try:
                response = requests.post(
                    f"{self.base_url}/chat/completions",
                    headers=self.headers,
                    json=data,
                    timeout=30  # 添加超时设置
                )

                # 检查响应状态
                if response.status_code != 200:
                    logger.error(f"API请求失败 - 状态码: {response.status_code}, 响应: {response.text}")
                    return "抱歉，图片识别服务暂时不可用"

                # 处理响应
                result = response.json()
                if 'choices' not in result or not result['choices']:
                    logger.error(f"API响应格式异常: {result}")
                    return "抱歉，无法解析图片内容"

                recognized_text = result['choices'][0]['message']['content']

                # 处理表情包识别结果
                if is_emoji:
                    if "最后一张表情包是" in recognized_text:

                        # 这个split("最后一张表情包是", 1)[1]，用这个字符串分割原本的字符串，最大分割次数为1，
                        # 然后取分割后的第二个部分
                        # 如 原本为 最后一张表情包是一只戴着墨镜的柴犬，表情很拽"
                        # 截取之后为 ["", "一只戴着墨镜的柴犬，表情很拽"]  去掉了指定字符之前的
                        recognized_text = recognized_text.split("最后一张表情包是", 1)[1].strip()
                    recognized_text = "用户发送了一张表情包，表情包的内容是：：" + recognized_text
                else:
                    recognized_text = "用户发送了一张照片，照片的内容是：" + recognized_text

                logger.info(f"Moonshot AI图片识别结果: {recognized_text}")
                return recognized_text

            except requests.exceptions.Timeout:
                logger.error("API请求超时")
                return "抱歉，图片识别服务响应超时"
            except requests.exceptions.RequestException as e:
                logger.error(f"API请求异常: {str(e)}")
                return "抱歉，图片识别服务出现错误"
            except Exception as e:
                logger.error(f"处理API响应失败: {str(e)}")
                return "抱歉，处理图片识别结果时出现错误"

        except Exception as e:
            logger.error(f"图片识别过程失败: {str(e)}", exc_info=True)
            return "抱歉，图片识别过程出现错误"

    # 这个调用图像识别的类好混乱，下面这个函数看起来是想做一个统一的调用接口，但之前的函数却都没用
    # 都是直接写在函数里面调用
    def chat_completion(self, messages: list, **kwargs) -> Optional[str]:
        """发送聊天请求到 Moonshot AI"""
        try:
            data = {
                "model": self.model,
                "messages": messages,
                "temperature": kwargs.get('temperature', self.temperature)
            }

            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=self.headers,
                json=data
            )
            response.raise_for_status()

            result = response.json()
            return result['choices'][0]['message']['content']

        except Exception as e:
            logger.error(f"图像识别服务请求失败: {str(e)}")
            return None