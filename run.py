"""
主程序入口文件
负责启动聊天机器人程序，包括:
- 初始化Python路径
- 禁用字节码缓存
- 清理缓存文件
- 启动主程序
"""

import os
import sys
import time
from colorama import init
import codecs
from src.utils.console import print_status, print_banner

# sys是python中的一个内置库，他可以获取python解释器的相关功能的操作，
# sys.platform是获取当前系统平台的信息，
# 设置系统默认编码为 UTF-8
# sys.stdout是标准输出流对象，加了buffer属性后可以将输出流转换为二进制流，
# sys.stderr是标准错误流对象
# 并且这段代码不属于任何函数和类，他在库导入完成后就会执行，并不依赖main函数
# 但也可以写到函数中
if sys.platform.startswith('win'):
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer)
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer)


# init是colorama库中的一个函数，用于初始化colorama库，这个库是用来美化
# 终端，在这里，他是用来支持print_status函数，输出带颜色的状态信息（成功，错误）

# 初始化colorama
init()

# 这个设置类似于java中，运行后会产生class文件，这里就是禁止生成，但java中的class
# 文件是必须的，但python中生辰的字节码可以加速程序运行，所以可以禁止生成

# 禁止生成__pycache__文件夹
sys.dont_write_bytecode = True

# os.path.abspath获取当前文件的绝对路径
# os.path.dirname如果给出的路径是文件，获取目录，如果是目录，获取上一层目录
# 然后将目录和src目录拼接，得到src目录的绝对路径，
# 这样做是为了在其他py文件中导入src目录中的其他模块时，能直接导入而不写路径
# 在我自己一般写的python项目中，一般不写这个，在其他py文件导入也是从src目录开始的
# 这是因为我自己的项目是在idea的集成环境运行，而不是直接在终端运行，所以这个需要
# 并且这个设置是全局生效的,因为设置在了python的解释器上,而这个项目中,
# 本文件是所有其他python文件的入口,所以其他文件也会继承这个python解释器,
# 如果其他文件可以单独启动,那就是不同的解释器了

# 将项目根目录添加到Python路径
root_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(root_dir)


# 将src目录添加到Python路径
src_path = os.path.join(root_dir, 'src')
sys.path.append(src_path)

def initialize_system():
    """初始化系统"""
    try:
        # 开头导入，程序启动即导入，作用域整个文件
        # 函数内导入，函数执行时导入，作用域本函数

        from src.utils.cleanup import cleanup_pycache
        from src.main import main
        from src.autoupdate.updater import Updater  # 导入更新器

        # 打印了一个banner，并且这个banner是写的一个函数，自己写出来的
        # 从项目的console文件导入，在开头有导入记录

        print_banner()

        # 这里生成了带颜色和图标的文字，蓝色，有info控制，图标为小火箭，由LAUNCH控制
        print_status("系统初始化中...", "info", "LAUNCH")
        # 生成了一行50个连续的减号，就像这样 --------------------------
        print("-" * 50)

        # 检查Python路径
        print_status("检查系统路径...", "info", "FILE")
        if src_path not in sys.path:
            print_status("添加src目录到Python路径", "info", "FILE")
        print_status("系统路径检查完成", "success", "CHECK")

        # 检查缓存设置
        print_status("检查缓存设置...", "info", "CONFIG")
        if sys.dont_write_bytecode:
            print_status("已禁用字节码缓存", "success", "CHECK")

        # 清理缓存文件
        print_status("清理系统缓存...", "info", "CLEAN")
        try:

            # 这里递归清理了所有的__pycache__文件夹，从根目录向下三层
            cleanup_pycache()
            
            from src.utils.logger import LoggerConfig
            from src.utils.cleanup import CleanupUtils
            from src.handlers.image import ImageHandler
            from src.handlers.voice import VoiceHandler
            from src.config import config

            # src_path变量之前定位到了src目录，这里向上了一层，也就是到了根目录
            root_dir = os.path.dirname(src_path)

            logger_config = LoggerConfig(root_dir)
            cleanup_utils = CleanupUtils(root_dir)
            image_handler = ImageHandler(
                root_dir=root_dir,
                api_key=config.llm.api_key,
                base_url=config.llm.base_url,
                image_model=config.media.image_generation.model
            )
            voice_handler = VoiceHandler(
                root_dir=root_dir,
                tts_api_key=config.media.text_to_speech.tts_api_key
            )

            # 下面是清理了一些文件夹，包括日志，临时文件，图片缓存，语音缓存
            # 神奇的是，按照代码中所写的内容，这个项目应该是支持
            # 图片识别，图片生成，语音生成
            # 语音识别的部分还没见到
            logger_config.cleanup_old_logs()
            cleanup_utils.cleanup_all()
            image_handler.cleanup_temp_dir()
            voice_handler.cleanup_voice_dir()
            
            # 清理更新残留文件
            print_status("清理更新残留文件...", "info", "CLEAN")
            try:

                # 更新用的,我懒得细看
                updater = Updater()


                updater.cleanup()  # 调用清理功能
                print_status("更新残留文件清理完成", "success", "CHECK")
            except Exception as e:
                print_status(f"清理更新残留文件失败: {str(e)}", "warning", "CROSS")
                
        except Exception as e:
            print_status(f"清理缓存失败: {str(e)}", "warning", "CROSS")
        print_status("缓存清理完成", "success", "CHECK")

        # 检查必要目录
        print_status("检查必要目录...", "info", "FILE")
        required_dirs = ['data', 'logs', 'src/config']
        for dir_name in required_dirs:
            dir_path = os.path.join(os.path.dirname(src_path), dir_name)
            if not os.path.exists(dir_path):
                os.makedirs(dir_path)
                print_status(f"创建目录: {dir_name}", "info", "FILE")
        print_status("目录检查完成", "success", "CHECK")

        print("-" * 50)
        print_status("系统初始化完成", "success", "STAR_1")
        time.sleep(1)  # 稍微停顿以便用户看清状态

        # 启动主程序
        print_status("启动主程序...", "info", "LAUNCH")
        print("=" * 50)
        main()

    except ImportError as e:
        print_status(f"导入模块失败: {str(e)}", "error", "CROSS")
        sys.exit(1)
    except Exception as e:
        print_status(f"初始化失败: {str(e)}", "error", "ERROR")
        sys.exit(1)

# 下面这段代码,可以在idea中直接运行,也可以在命令行通过命令来运行本脚本,下面代码都是执行
# 除此之外，在程序正式运行的过程中，下面的代码都不会运行

if __name__ == '__main__':

    try:
        print_status("启动聊天机器人...", "info", "BOT")
        initialize_system()
    except KeyboardInterrupt:
        print("\n")
        print_status("正在关闭系统...", "warning", "STOP")
        print_status("感谢使用，再见！", "info", "BYE")
        print("\n")
    except Exception as e:
        print_status(f"系统错误: {str(e)}", "error", "ERROR")
        sys.exit(1) 
