from core.print import print_warning
from driver.base import WX_API
from core.config import cfg
from jobs.notice import sys_notice
from driver.success import Success
from tools.base64_tools import image_to_base64
import time

def send_wx_code(title:str="",url:str=""):
    if cfg.get("server.send_code",False):
        WX_API.GetCode(Notice=CallBackNotice,CallBack=Success)
    pass
def CallBackNotice(data=None,ext_data=None):
        if data is not None:
            print_warning(data)
            return 
        img_path=WX_API.QRcode()['code']
        rss_domain=str(cfg.get("rss.base_url",""))
        url=rss_domain+str(img_path)
        qr_image_path = getattr(WX_API, "wx_login_path", None) or getattr(WX_API, "qr_code_path", "./static/wx_qrcode.png")
        url=image_to_base64(qr_image_path)
        text=f"- 服务名：{cfg.get('server.name','')}\n"
        text+=f"- 发送时间： {time.strftime('%Y-%m-%d %H:%M:%S',time.localtime(time.time()))}"
        if WX_API.GetHasCode():
            text+=f"![描述]({url})"
            # text+=f"<img src='{url}' width='100' height='100'/>"
            text+=f"\n- 请使用微信扫描二维码，恢复讲座数据抓取授权"
        sys_notice(text, str(cfg.get("server.code_title","浙大活动授权已失效，请重新扫码")))
