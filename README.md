# KouriChat - 虚拟伴侣

这是一个基于大模型实现的虚拟伴侣,实现微信聊天功能

核心依赖wxauto(微信调用)和deepseek(生成回复),.moonshot(月之暗面,图片识别)

目前大模型回复能力无法睥睨真人,原因在于大模型没有长期记忆能力,因此该项目加入了短期,长期记忆
该本部分可查看 llm_service.py的get_response函数即可理解

本项目仅用作个人学习python之用



