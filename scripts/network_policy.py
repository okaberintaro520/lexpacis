"""No proxy installation or tunnelling. Reject unsafe destinations and redirects."""
import ipaddress
import socket
import urllib.parse
import urllib.request

def validate_public_url(url,allowed_hosts):
    parsed=urllib.parse.urlsplit(url)
    if parsed.scheme not in ('https','http') or parsed.username or parsed.password or not parsed.hostname:
        raise ValueError('仅允许无嵌入凭证的 HTTP(S) 官方地址')
    if parsed.hostname.lower() not in allowed_hosts or parsed.port not in (None,80,443):
        raise ValueError('只允许已登记的官方主机与标准端口')
    addresses=socket.getaddrinfo(parsed.hostname,parsed.port or (443 if parsed.scheme=='https' else 80),type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(row[4][0]).is_global for row in addresses):
        raise ValueError('连接被安全策略拒绝：域名解析到本地、私有或保留地址；未绕过')
    return url

class RestrictedRedirect(urllib.request.HTTPRedirectHandler):
    def __init__(self,hosts):self.hosts=hosts
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        if urllib.parse.urlsplit(req.full_url).scheme=='https' and urllib.parse.urlsplit(newurl).scheme!='https':
            raise ValueError('拒绝 HTTPS 降级为 HTTP 的重定向')
        validate_public_url(newurl,self.hosts)
        return super().redirect_request(req,fp,code,msg,headers,newurl)
