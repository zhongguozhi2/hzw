import paramiko
import socks

# ssh -o ProxyCommand="nc -x 172.17.9.194:28673 %h %p" cbcadmin@172.17.9.32 -p 6188

# ===== 代理信息（等价 nc -x）=====
PROXY_HOST = "172.17.9.194"
PROXY_PORT = 28673

# ===== 目标 SSH =====
TARGET_HOST = "172.17.9.32"
TARGET_PORT = 6188
USERNAME = "cbcadmin"
PASSWORD = "eIuSUhVnTD"   # 或使用 key

# 创建 SOCKS5 代理 socket
sock = socks.socksocket()
sock.set_proxy(
    proxy_type=socks.SOCKS5,
    addr=PROXY_HOST,
    port=PROXY_PORT
)

# 通过代理连接目标
sock.connect((TARGET_HOST, TARGET_PORT))

# Paramiko SSH
client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(
    hostname=TARGET_HOST,
    port=TARGET_PORT,
    username=USERNAME,
    password=PASSWORD,
    sock=sock
)

stdin, stdout, stderr = client.exec_command("whoami")
print(stdout.read().decode())

client.close()
