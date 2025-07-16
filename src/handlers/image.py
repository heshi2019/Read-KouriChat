"""
图像处理模块
负责处理图像相关功能，包括:
- 图像生成请求识别
- 随机图片获取
- API图像生成
- 临时文件管理
"""

import os
import logging
import requests
from datetime import datetime
from typing import Optional, List, Tuple
import re
import time
from src.services.ai.llm_service import LLMService

# 获取日志记录器，如果这个名字存在，则获取，不存在则创建

# 修改logger获取方式，确保与main模块一致
logger = logging.getLogger('main')

class ImageHandler:
    def __init__(self, root_dir, api_key, base_url, image_model):
        self.root_dir = root_dir
        self.api_key = api_key
        self.base_url = base_url
        self.image_model = image_model
        self.temp_dir = os.path.join(root_dir, "data", "images", "temp")

        # 复用消息模块的AI实例(使用正确的模型名称)
        from config import config
        self.text_ai = LLMService(
            api_key=api_key,
            base_url=base_url,
            model="kourichat-vision",
            max_token=2048,
            temperature=0.5,
            max_groups=15
        )

        # 这里字典的值是一个字符串，使用了括号括起来了，括号的作用就是连接多个字符串
        # 多语言提示模板
        self.prompt_templates = {
            'basic': (
                "请将以下图片描述优化为英文提示词，包含：\n"
                "1. 主体细节（至少3个特征）\n"
                "2. 环境背景\n"
                "3. 艺术风格\n"
                "4. 质量参数\n"
                "示例格式：\"A..., ... , ... , digital art, trending on artstation\"\n"
                "原描述：{prompt}"
            ),
            'creative': (
                "你是一位专业插画师，请用英文为以下主题生成详细绘画提示词：\n"
                "- 核心元素：{prompt}\n"
                "- 需包含：构图指导/色彩方案/光影效果\n"
                "- 禁止包含：水印/文字/低质量描述\n"
                "直接返回结果"
            )
        }

        # 质量分级？负面提示词？这是什么模型的调用要求吗

        # 质量分级参数配置
        self.quality_profiles = {
            'fast': {'steps': 20, 'width': 768},
            'standard': {'steps': 28, 'width': 1024},
            'premium': {'steps': 40, 'width': 1280}
        }

        # 通用负面提示词库（50+常见词条）
        self.base_negative_prompts = [
            "low quality", "blurry", "ugly", "duplicate", "poorly drawn",
            "disfigured", "deformed", "extra limbs", "mutated hands",
            "poor anatomy", "cloned face", "malformed limbs",
            "missing arms", "missing legs", "extra fingers",
            "fused fingers", "long neck", "unnatural pose",
            "low resolution", "jpeg artifacts", "signature",
            "watermark", "username", "text", "error",
            "cropped", "worst quality", "normal quality",
            "out of frame", "bad proportions", "bad shadow",
            "unrealistic", "cartoonish", "3D render",
            "overexposed", "underexposed", "grainy",
            "low contrast", "bad perspective", "mutation",
            "childish", "beginner", "amateur"
        ]

        # 动态负面提示词生成模板
        self.negative_prompt_template = (
            "根据以下图片描述，生成5个英文负面提示词（用逗号分隔），避免出现：\n"
            "- 与描述内容冲突的元素\n"
            "- 重复通用负面词\n"
            "描述内容：{prompt}\n"
            "现有通用负面词：{existing_negatives}"
        )

        # 提示词扩展触发条件
        self.prompt_extend_threshold = 30  # 字符数阈值

        # 这里会创建一连串目录，用于存图片，这个目录后续会通过其他函数删除
        os.makedirs(self.temp_dir, exist_ok=True)

     # 下面这个函数的定义后加了箭头，箭头后表示的是本函数的返回值类型，同样，
     # 这个返回值类型也是建议，不强制要求，就算返回str也不会报错

    def is_random_image_request(self, message: str) -> bool:
        """检查消息是否为请求图片的模式"""
        # 基础词组
        basic_patterns = [
            r'来个图',
            r'来张图',
            r'来点图',
            r'想看图',
        ]

        # 将消息转换为小写以进行不区分大小写的匹配
        message = message.lower()

        # 这是一个检查消息里面是否有basic_patterns 这个列表中的元素
        # 下面的这种写法称为高效模式匹配写法 等价于
        # for pattern in basic_patterns
        #     if pattern in message:
        #         return True
        # any(...) → 只要有一个模式匹配成功就返回 True

        # 1. 检查基础模式
        if any(pattern in message for pattern in basic_patterns):
            return True

        # 2. 检查更复杂的模式
        complex_patterns = [
            r'来[张个幅]图',
            r'发[张个幅]图',
            r'看[张个幅]图',
        ]

        # 这里主要用到了re.search 函数，这个函数的作用是在字符串中搜索正则表达式模式
        # 而正则表达式在上面  complex_patterns 列表中，每个元素中用方括号括起来了
        # 列表的元素中的 [] 就是正则表达式，表示匹配其中任意字符
        if any(re.search(pattern, message) for pattern in complex_patterns):
            return True

        return False

    # Optional和Union，这两个关键字都是表示参数可以是多种类型的，
    # 区别在于Optional表示参数可以是None，而Union表示参数可以是多种类型中的一种
    # 这里的Optional[str]表示返回值可以是str类型，也可以是None类型
    # 这里的Optional[str]等价于str | None

    # 也就是说，这个方法通过随机api获取了一张图片并进行了保存,方法返回了图片路径，为什么要这样做
    def get_random_image(self) -> Optional[str]:
        """从API获取随机图片并保存"""
        try:
            if not os.path.exists(self.temp_dir):
                os.makedirs(self.temp_dir)

            # https://t.mwm.moe   这是一个获取随机图片的网站，主要为二次元图片

            # 获取图片链接
            response = requests.get('https://t.mwm.moe/pc')
            if response.status_code == 200:

                # time.time() 获取当前时间戳，这个time库是官方内置的库
                # 生成唯一文件名
                timestamp = int(time.time())
                image_path = os.path.join(self.temp_dir, f'image_{timestamp}.jpg')

                # 保存图片
                with open(image_path, 'wb') as f:
                    f.write(response.content)

                return image_path
        except Exception as e:
            logger.error(f"获取图片失败: {str(e)}")
        return None

    def is_image_generation_request(self, text: str) -> bool:
        """判断是否为图像生成请求"""

        # 用不同的列表,存储动词,名词,然后和用户输入的文本进行匹配,如果匹配到了
        # 表示用户需要生成图片,这怎么感觉怪怪的

        # 基础动词
        draw_verbs = ["画", "绘", "生成", "创建", "做"]

        # 图像相关词
        image_nouns = ["图", "图片", "画", "照片", "插画", "像"]

        # 数量词
        quantity = ["一下", "一个", "一张", "个", "张", "幅"]

        # 组合模式
        patterns = [
            r"画.*[猫狗人物花草山水]",
            r"画.*[一个张只条串份副幅]",
            r"帮.*画.*",
            r"给.*画.*",
            r"生成.*图",
            r"创建.*图",
            r"能.*画.*吗",
            r"可以.*画.*吗",
            r"要.*[张个幅].*图",
            r"想要.*图",
            r"做[一个张]*.*图",
            r"画画",
            r"画一画",
        ]

        # 1. 检查正则表达式模式
        if any(re.search(pattern, text) for pattern in patterns):
            return True

        # 2. 检查动词+名词组合
        for verb in draw_verbs:
            for noun in image_nouns:
                if f"{verb}{noun}" in text:
                    return True
                # 检查带数量词的组合
                for q in quantity:
                    if f"{verb}{q}{noun}" in text:
                        return True
                    if f"{verb}{noun}{q}" in text:
                        return True

        # 3. 检查特定短语
        special_phrases = [
            "帮我画", "给我画", "帮画", "给画",
            "能画吗", "可以画吗", "会画吗",
            "想要图", "要图", "需要图",
        ]

        if any(phrase in text for phrase in special_phrases):
            return True

        return False

    def _expand_prompt(self, prompt: str) -> str:
        """使用AI模型扩展简短提示词"""
        try:
            if len(prompt) >= 30:  # 长度足够则不扩展
                return prompt

            # 这里调用了大模型,用来扩展提示词,也就是 prompt_templates 字典的 basic 键的值
            response = self.text_ai.chat(
                messages=[{"role": "user", "content": self.prompt_templates['basic'].format(prompt=prompt)}],
                temperature=0.7
            )

            # 移除返回数据开头结尾的空白符,或者返回原本提示词
            return response.strip() or prompt
        except Exception as e:
            logger.error(f"提示词扩展失败: {str(e)}")
            return prompt

    def _translate_prompt(self, prompt: str) -> str:
        """简单中译英处理（实际可接入翻译API）"""
        # 简易替换常见中文词汇
        translations = {
            "女孩": "girl",
            "男孩": "boy",
            "风景": "landscape",
            "赛博朋克": "cyberpunk",
            "卡通": "cartoon style",
            "写实": "photorealistic",
        }
        for cn, en in translations.items():
            # replace替换,将prompt这个变量(句子)中,所有在translations字典中的中文替换为英文
            prompt = prompt.replace(cn, en)
        return prompt

    def _generate_dynamic_negatives(self, prompt: str) -> List[str]:
        """生成动态负面提示词"""
        try:
            # 获取现有通用负面词前10个作为示例
            existing_samples = ', '.join(self.base_negative_prompts[:10])

            # 这就是构建了一个请求API,有具体的请求内容,但这负面词是什么
            response = self.text_ai.chat([{
                "role": "user",
                "content": self.negative_prompt_template.format(
                    prompt=prompt,
                    existing_negatives=existing_samples
                )
            }])

            # 解析响应并去重
            generated = [n.strip().lower() for n in response.split(',')]

            # 转为集合去重，再转为列表返回
            return list(set(generated))
        except Exception as e:
            logger.error(f"动态负面词生成失败: {str(e)}")
            return []

    def _build_final_negatives(self, prompt: str) -> str:
        """构建最终负面提示词"""

        # 这里将原本的负面词列表转为了集合
        # 始终包含基础负面词
        final_negatives = set(self.base_negative_prompts)

        # 提示词小于30个字符时触发
        # 当提示词简短时触发动态生成
        if len(prompt) <= self.prompt_extend_threshold:
            dynamic_negatives = self._generate_dynamic_negatives(prompt)

            # 将提示词给AI做扩展，将扩展后的词加入到本函数的集合中
            final_negatives.update(dynamic_negatives)

        return ', '.join(final_negatives)

    # Tuple表示元组，元组为不可变的有序序列
    def _optimize_prompt(self, prompt: str) -> Tuple[str, str]:
        """多阶段提示词优化"""
        try:
            # 第一阶段：基础优化
            stage1 = self.text_ai.chat([{
                "role": "user",
                "content": self.prompt_templates['basic'].format(prompt=prompt)
            }])

            # 第二阶段：创意增强
            stage2 = self.text_ai.chat([{
                "role": "user",
                "content": self.prompt_templates['creative'].format(prompt=prompt)
            }])

            # 混合策略：取两次优化的关键要素
            final_prompt = f"{stage1}, {stage2.split(',')[-1]}"

            # 返回数据类型为元组
            return final_prompt, "multi-step"

        except Exception as e:
            logger.error(f"提示词优化失败: {str(e)}")
            return prompt, "raw"

    def _select_quality_profile(self, prompt: str) -> dict:
        """根据提示词复杂度选择质量配置"""

        # 根据输入参数的长度，返回 quality_profiles 字典不同的数字
        word_count = len(prompt.split())
        if word_count > 30:
            return self.quality_profiles['premium']
        elif word_count > 15:
            return self.quality_profiles['standard']
        return self.quality_profiles['fast']

    def generate_image(self, prompt: str) -> Optional[str]:
        """整合版图像生成方法"""
        try:
            # 自动扩展短提示词
            if len(prompt) <= self.prompt_extend_threshold:

                # 如果提示词少于30个，让AI描述图片
                prompt = self._expand_prompt(prompt)

            # 有点重复，上面的 _expand_prompt方法就已经让AI描述图片了，下面的 _optimize_prompt
            # 函数有让AI描述了一次

            # 多阶段提示词优化
            optimized_prompt, strategy = self._optimize_prompt(prompt)
            logger.info(f"优化策略: {strategy}, 优化后提示词: {optimized_prompt}")

            # 构建负面提示词
            negative_prompt = self._build_final_negatives(optimized_prompt)
            logger.info(f"最终负面提示词: {negative_prompt}")

            # 质量配置选择
            quality_config = self._select_quality_profile(optimized_prompt)
            logger.info(f"质量配置: {quality_config}")

            # 构建请求参数
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }

            payload = {
                "model": self.image_model,
                "prompt": f"masterpiece, best quality, {optimized_prompt}",
                "negative_prompt": negative_prompt,
                "steps": quality_config['steps'],
                "width": quality_config['width'],
                "height": quality_config['width'],  # 保持方形比例
                "guidance_scale": 7.5,
                "seed": int(time.time() % 1000)  # 添加随机种子
            }

            # 这里构建的所有请求参数，都是从run.py文件中传递，
            # 再追数据配置在src.config下，也就是从浏览器看到的配置页

            # 调用生成API
            response = requests.post(
                f"{self.base_url}/images/generations",
                headers=headers,
                json=payload,
                timeout=45
            )
            response.raise_for_status()

            # 结果处理
            result = response.json()
            if "data" in result and len(result["data"]) > 0:
                img_url = result["data"][0]["url"]
                img_response = requests.get(img_url)
                if img_response.status_code == 200:

                    # 获取当前时间做文件名
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    temp_path = os.path.join(self.temp_dir, f"image_{timestamp}.jpg")
                    with open(temp_path, "wb") as f:
                        f.write(img_response.content)
                    logger.info(f"图片已保存到: {temp_path}")
                    return temp_path
            logger.error("API返回的数据中没有图片URL")
            return None

        except Exception as e:
            logger.error(f"图像生成失败: {str(e)}")
            return None

    def cleanup_temp_dir(self):
        """清理临时目录中的旧图片"""
        try:
            if os.path.exists(self.temp_dir):
                for file in os.listdir(self.temp_dir):
                    file_path = os.path.join(self.temp_dir, file)
                    try:
                        if os.path.isfile(file_path):
                            os.remove(file_path)
                            logger.info(f"清理旧临时文件: {file_path}")
                    except Exception as e:
                        logger.error(f"清理文件失败 {file_path}: {str(e)}")
        except Exception as e:
            logger.error(f"清理临时目录失败: {str(e)}")
