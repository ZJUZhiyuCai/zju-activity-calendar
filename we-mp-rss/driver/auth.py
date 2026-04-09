import threading
from core.print import print_warning
from core.runtime_flags import is_auth_refresh_enabled
from driver.base import WX_InterFace
import os
import portalocker
from core.task import TaskScheduler
from driver.success import Success

def auth():
    def run_auth():
        wx=WX_InterFace()
        # wx.Token(callback=Success)
        wx.switch_account()
    
    thread = threading.Thread(target=run_auth)
    thread.start()
    thread.join()  # 可选：等待完成
def start_auth_service(*, force_schedule: bool = False):    
    from driver.wx_api import login_with_token
    login_with_token()
    if is_auth_refresh_enabled(force=force_schedule):
        print_warning("启动授权定时任务")
        auth_task=TaskScheduler()
        auth_task.clear_all_jobs()
        print("是否开启调试模式:",str(os.getenv('DEBUG',False)))
        if str(os.getenv('DEBUG',False))=="True":
            auth_task.add_cron_job(auth, "*/10 * * * *",tag="授权定时更新")
        else:
            auth_task.add_cron_job(auth, "0 0 */1 * *",tag="授权定时更新")
        auth_task.start()
