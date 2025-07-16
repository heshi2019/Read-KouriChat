"""
自动发送消息处理模块
负责处理自动发送消息的逻辑，包括:
- 倒计时管理
- 消息发送
- 安静时间控制
"""

import logging
import random
import threading
from datetime import datetime, timedelta

logger = logging.getLogger('main')

class AutoSendHandler:
    def __init__(self, message_handler, config, listen_list):
        self.message_handler = message_handler
        self.config = config
        self.listen_list = listen_list
        
        # 计时器相关
        self.countdown_timer = None
        self.is_countdown_running = False
        self.countdown_end_time = None
        self.unanswered_count = 0
        self.last_chat_time = None

    def update_last_chat_time(self):
        """更新最后一次聊天时间"""
        self.last_chat_time = datetime.now()
        self.unanswered_count = 0
        logger.info(f"更新最后聊天时间: {self.last_chat_time}，重置未回复计数器为0")

    def is_quiet_time(self) -> bool:
        """检查当前是否在安静时间段内"""
        try:
            # 现在时间
            current_time = datetime.now().time()
            # 安静开始时间
            quiet_start = datetime.strptime(self.config.behavior.quiet_time.start, "%H:%M").time()
            # 安静结束时间
            quiet_end = datetime.strptime(self.config.behavior.quiet_time.end, "%H:%M").time()

            # 这里假设安静时间是早8点到22点，则为不跨天，可以直接比较
            if quiet_start <= quiet_end:
                # 如果安静时间不跨天
                return quiet_start <= current_time <= quiet_end
            else:
                # 如果安静时间跨天（比如22:00到次日08:00）
                return current_time >= quiet_start or current_time <= quiet_end
        except Exception as e:
            logger.error(f"检查安静时间出错: {str(e)}")
            return False

    def get_random_countdown_time(self):
        """获取随机倒计时时间"""
        min_seconds = int(self.config.behavior.auto_message.min_hours * 3600)
        max_seconds = int(self.config.behavior.auto_message.max_hours * 3600)

        # uniform返回最小和最大时间之间的毫秒级浮点数
        return random.uniform(min_seconds, max_seconds)

    def auto_send_message(self):
        """自动发送消息"""
        if self.is_quiet_time():
            logger.info("当前处于安静时间，跳过自动发送消息")

            # 这里是，判断是否为安静时间，如果是，则重新开始倒计时
            self.start_countdown()
            return

        # listen_list是监听列表，配置在config.json中，是一个列表，里面是微信用户名
        if self.listen_list:

            # random.choice随机返回参数中的一个元素，也就是随机返回一个微信用户名
            user_id = random.choice(self.listen_list)
            # 这个计数器是做什么的，哦，这是用户没有回复消息的次数
            self.unanswered_count += 1

            # 这里拼接了一个字符出串
            # 请你模拟系统设置的角色，根据之前的聊天内容在微信上找对方发消息想知道对方在做什么，并跟对方报备自己在做什么、什么心情，语气自然，与之前的不要重复
            # 这是对方第 x 次未回复你, 你可以选择模拟对方未回复后的小脾气

reply_content = f"{self.config.behavior.auto_message.content} 这是对方可能因为在忙碌或者有自己的事没有回复你，根据上下文联系，判断用户现在的状态，回复符合角色的话语。"
            logger.info(f"自动发送消息到 {user_id}: {reply_content}")
            try:

                # 这个message_handler是一个非常复杂的类，看起来好像是处理AI消息的
                self.message_handler.add_to_queue(
                    chat_id=user_id,
                    content=reply_content,
                    sender_name="System",
                    username="System",
                    is_group=False
                )

                # 又重新开始倒计时
                # 这两个函数是互相调用的，一个环，start_countdown -> auto_send_message -> start_countdown
                # 倒计时 -> 自动发送消息 -> 倒计时
                self.start_countdown()
            except Exception as e:
                logger.error(f"自动发送消息失败: {str(e)}")
                self.start_countdown()
        else:
            logger.error("没有可用的聊天对象")
            self.start_countdown()

    def start_countdown(self):
        """开始新的倒计时"""
        if self.countdown_timer:

            # cancel是timer类的一个方法，用于取消和销毁之前的定时器，这个方法是异步的，
            # 但这个countdown_timer变量在init函数定义的时候并没有具体的类型
            self.countdown_timer.cancel()

        # 一个随机的毫秒时间
        countdown_seconds = self.get_random_countdown_time()

        # 新的倒计时？这是干什么的
        self.countdown_end_time = datetime.now() + timedelta(seconds=countdown_seconds)
        logger.info(f"开始新的倒计时: {countdown_seconds/3600:.2f}小时")

        # threading.Timer存在于python标准库，用于创建一个线程安全的定时器
        # 在countdown_seconds时间之后，自动调用auto_send_message函数
        self.countdown_timer = threading.Timer(countdown_seconds, self.auto_send_message)
        # 守护线程
        self.countdown_timer.daemon = True
        # 启动
        self.countdown_timer.start()
        # 是否运行标志位
        self.is_countdown_running = True

    def stop(self):
        """停止自动发送消息"""
        if self.countdown_timer:
            self.countdown_timer.cancel()
            self.countdown_timer = None
        self.is_countdown_running = False
        logger.info("自动发送消息已停止") 