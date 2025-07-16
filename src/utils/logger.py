"""
日志工具模块
提供日志记录功能，包括:
- 日志配置管理
- 日志文件轮转
- 日志清理
- 多级别日志记录
"""

import logging
import os
from logging.handlers import RotatingFileHandler
from datetime import datetime
from typing import Optional

class LoggerConfig:

    # root_dir: str 函数的这个参数挺好玩的，他类似于java 的泛型指定参数类型
    # 这里是指定了root_dir 这个参数的类型为str，
    # 实际传入其他类型（如 int）也不会报错，但 IDE/静态检查工具会警告

    def __init__(self, root_dir: str):
        self.root_dir = root_dir
        self.log_dir = os.path.join(root_dir, "logs")

        # 这个函数是检查了 log_dir 这个目录是否存在，如果不存在，就创建这个目录
        # 目录为根目录下的logs目录
        self.ensure_log_dir()

    # 在java中，类变量是本类中的所有函数都可以直接访问的，但在python中
    # 类的变量是需要在init初始化函数中定义，并且其他函数，不论是否需要使用
    # 到这些变量，都需要在函数定义的形参中，写上self

    def ensure_log_dir(self):
        """确保日志目录存在"""
        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir)

    def get_log_file(self):

        # current_date变量获取了当前时间，格式为20200101这样，用strftime函数做了格式化，

        """获取日志文件路径"""
        current_date = datetime.now().strftime("%Y%m%d")

        # 拼接了日志目录和日志文件名，
        # 日志文件名格式为bot_20200101.log，其中20200101为当前日期
        return os.path.join(self.log_dir, f"bot_{current_date}.log")

    # name: Optional[str] = None  表示，参数name传入的数据类型是str 或者 None，并且默认值为None
    # level: int = logging.INFO  表示，参数 level传入的数据类型为int，默认值为20
    # logging.INFO 是 python内置的logging模块的一个常量，值为20


    # logging.CRITICAL = 50
    # logging.ERROR = 40
    # logging.WARNING = 30
    # logging.INFO = 20  # ← 这里使用的默认值
    # logging.DEBUG = 10
    # logging.NOTSET = 0


    def setup_logger(self, name: Optional[str] = None, level: int = logging.INFO):

        """配置日志记录器"""
        # 创建或获取日志记录器

        # 创建日志记录器
        logger = logging.getLogger(name)
        # 设置日志级别，他是用数字来控制的，上面注释有
        logger.setLevel(level)
        # 允许日志传播到父记录器，这个好像会影响到日志的处理，每个日志记录器有一个handlers
        # 用来处理日志，如果传播，则会让父类日志记录器的handlers也处理
        logger.propagate = True  # 确保日志能正确传播
        
        # 移除所有已有的handler，防止重复
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)

        # 这里创建的日志处理2器，将日志输出到终端命令行（StreamHandler）中
        # 设置了日志级别（默认为info），格式（Formatter）

        # 创建控制台处理器
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        console_formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s'
        )
        # 设置格式
        console_handler.setFormatter(console_formatter)
        # 日志新增处理器，
        logger.addHandler(console_handler)

        # 日志的Handler就是下面创建的这个，称为日志处理器，
        # 主要作用是管理日志输出目的地，设置日志格式等

        # RotatingFileHandler是文件大小轮转处理器，这里设置了
        # 文件名，文件大小，备份数量，编码格式
        # 这是的文件大小，单天是10m，如果超过，会自动创建新的同名日志文件
        # 在文件名后加.1

        # 创建文件处理器
        file_handler = RotatingFileHandler(
            self.get_log_file(),
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5,
            encoding='utf-8'
        )
        file_handler.setLevel(level)
        file_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

        return logger

    def cleanup_old_logs(self, days: int = 7):
        """清理指定天数之前的日志文件"""
        try:
            current_date = datetime.now()

            # 列出当前目录下的所有文件和目录，如果文件名中不包含 bot_ 和 .log，则跳过（日志文件命名规范）
            for filename in os.listdir(self.log_dir):
                if not filename.startswith("bot_") or not filename.endswith(".log"):
                    continue

                # 拼接日志完整路径
                file_path = os.path.join(self.log_dir, filename)

                file_date_str = filename[4:12]  # 提取日期部分 YYYYMMDD
                try:
                    # 这里将日期还原为了一个对象，用strptime函数实现
                    file_date = datetime.strptime(file_date_str, "%Y%m%d")
                    # 这里用当前日期减去了文件日期，并获取差值天数
                    days_old = (current_date - file_date).days

                    # 如果超过指定天数，则删除该文件，默认7天
                    if days_old > days:
                        os.remove(file_path)
                        print(f"已删除旧日志文件: {filename}")
                except ValueError:
                    continue
        except Exception as e:
            print(f"清理日志文件失败: {str(e)}") 