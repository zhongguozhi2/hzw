from netmiko import ConnectHandler
import socks

# ssh -o ProxyCommand="nc -x 172.17.9.194:28673 %h %p" cbcadmin@172.17.9.32 -p 6188

# ===== SOCKS5 代理 =====
proxy_sock = socks.socksocket()
proxy_sock.set_proxy(
    socks.SOCKS5,
    "172.17.9.194",
    28673
)

# ===== 连接目标 =====
proxy_sock.connect(("172.17.9.32", 6188))

device = {
    "device_type": "vyos",
    "host": "172.17.9.32",
    "username": "cbcadmin",
    "password": "eIuSUhVnTD",
    "port": 6188,
    "sock": proxy_sock,
}

conn = ConnectHandler(**device)
output = conn.send_command("whoami")
print(output)
conn.disconnect()
