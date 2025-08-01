"""
清理工具模块
负责清理系统中的临时文件和缓存，包括:
- 清理wxauto文件夹
- 清理screenshot文件夹
- 清理__pycache__文件夹
- 提供统一的清理接口
"""

import os
import shutil
import logging
import time

# 获取了日志记录器的名字，这里的名字是当前模块的名字，也就是src.utils.cleanup
logger = logging.getLogger(__name__)

class CleanupUtils:
    def __init__(self, root_dir: str):
        self.root_dir = root_dir
        self.wxauto_dir = os.path.join(root_dir, "wxautoFiles")
        self.screenshot_dir = os.path.join(root_dir, "screenshot")

    def cleanup_wxauto_files(self):
        """清理wxauto文件夹"""
        try:
            logger.info(f"正在检查目录: {self.wxauto_dir}")
            if not os.path.exists(self.wxauto_dir):
                logger.info("wxauto文件夹不存在，无需清理")
                return
                
            max_retries = 3
            # 在python中，for循环的循环变量并不需要初始化 如这里的attempt
            # 而他的循环变量是 0,1,2 通过range函数产生
            for attempt in range(max_retries):
                try:

                    files = os.listdir(self.wxauto_dir)
                    if not files:
                        logger.info("wxauto文件夹为空，无需清理")
                        return
                        
                    deleted_count = 0
                    for file in files:
                        try:
                            # 拼接文件路径
                            file_path = os.path.join(self.wxauto_dir, file)
                            if os.path.isfile(file_path):
                                try:
                                    # 如果文件存在，修改权限为777，防止无法删除
                                    os.chmod(file_path, 0o777)
                                except:
                                    pass
                                # 删除文件
                                os.remove(file_path)
                                deleted_count += 1
                            elif os.path.isdir(file_path):
                                # 如果存在目录，直接递归删除
                                shutil.rmtree(file_path, ignore_errors=True)
                                deleted_count += 1
                        except PermissionError:
                            logger.warning(f"文件被占用，无法删除: {file_path}")
                            continue
                        except Exception as e:
                            logger.error(f"删除失败 {file_path}: {str(e)}")
                            continue
                            
                    try:
                        # 删除完文件夹中内容，将文件夹删除
                        if os.path.exists(self.wxauto_dir):
                            os.rmdir(self.wxauto_dir)
                            logger.info("成功删除wxauto文件夹")
                    except:
                        pass
                        
                    logger.info(f"清理完成，共删除 {deleted_count} 个文件/文件夹")
                    break
                    
                except Exception as e:
                    if attempt < max_retries - 1:
                        logger.warning(f"清理失败，正在重试 ({attempt + 1}/{max_retries})")
                        time.sleep(1)
                    else:
                        raise
                        
        except Exception as e:
            logger.error(f"清理wxauto文件夹时发生错误: {str(e)}")

    def cleanup_screenshot(self):
        """清理screenshot文件夹"""
        try:
            if os.path.isdir(self.screenshot_dir):
                shutil.rmtree(self.screenshot_dir)
                logger.info(f"目录 {self.screenshot_dir} 已成功删除")
            else:
                logger.info(f"目录 {self.screenshot_dir} 不存在，无需删除")
        except Exception as e:
            logger.error(f"清理screenshot目录失败: {str(e)}")

    def cleanup_update_files(self):
        """清理更新残留文件和目录"""
        try:
            # 清理backup目录
            backup_dir = os.path.join(self.root_dir, "backup")
            if os.path.exists(backup_dir):
                try:
                    shutil.rmtree(backup_dir)
                    logger.info(f"已清理备份目录: {backup_dir}")
                except Exception as e:
                    logger.error(f"清理备份目录失败: {str(e)}")
                    # 尝试使用系统命令强制删除
                    try:
                        import subprocess
                        if os.name == 'nt':  # Windows
                            subprocess.run(['rd', '/s', '/q', backup_dir], shell=True)
                        else:  # Linux/Mac
                            subprocess.run(['rm', '-rf', backup_dir])
                    except Exception as e2:
                        logger.error(f"使用系统命令清理备份目录失败: {str(e2)}")
            
            # 清理KouriChat-Kourichat-Festival-Test目录
            test_dir = os.path.join(self.root_dir, "KouriChat-Kourichat-Festival-Test")
            if os.path.exists(test_dir):
                try:
                    shutil.rmtree(test_dir)
                    logger.info(f"已清理测试目录: {test_dir}")
                except Exception as e:
                    logger.error(f"清理测试目录失败: {str(e)}")
                    # 尝试使用系统命令强制删除
                    try:
                        import subprocess
                        if os.name == 'nt':  # Windows
                            subprocess.run(['rd', '/s', '/q', test_dir], shell=True)
                        else:  # Linux/Mac
                            subprocess.run(['rm', '-rf', test_dir])
                    except Exception as e2:
                        logger.error(f"使用系统命令清理测试目录失败: {str(e2)}")
        except Exception as e:
            logger.error(f"清理更新残留文件失败: {str(e)}")

    def cleanup_all(self):
        """执行所有清理操作"""
        try:
            # 清理各个handler的临时目录
            self.cleanup_wxauto_files()
            # 清理pycache
            cleanup_pycache()
            # 清理screenshot文件夹
            self.cleanup_screenshot()
            # 清理更新残留文件
            self.cleanup_update_files()
            logger.info("所有清理操作完成")
        except Exception as e:
            logger.error(f"清理操作失败: {str(e)}")

def cleanup_pycache():
    """递归清理所有__pycache__文件夹"""
    root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    # os.walk，遍历给定的目录，并返回一个三元组 (dirpath, dirnames, filenames)，分别代表
    # 路径，目录，文件
    for root, dirs, files in os.walk(root_dir):
        if '__pycache__' in dirs:
            pycache_path = os.path.join(root, '__pycache__')
            try:
                # shutil内置库，rmtree递归删除
                shutil.rmtree(pycache_path)
                logger.info(f"已清理: {pycache_path}")
            except Exception as e:
                logger.error(f"清理失败 {pycache_path}: {str(e)}") 