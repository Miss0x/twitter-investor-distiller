import paramiko

HOST = "43.156.21.131"
USER = "root"
PASSWORD = "lwj657657--"

CMDS = [
    (
        "基本身份与家目录",
        "id; getent passwd lighthouse; getent passwd agentuser; ls -la /home; echo ----; ls -la /root",
    ),
    (
        "Hermes 相关进程与服务",
        "ps -ef | grep -i hermes | grep -v grep || true; echo ----; systemctl list-units --type=service --all | grep -i hermes || true; echo ----; systemctl list-unit-files | grep -i hermes || true",
    ),
    (
        "lighthouse 家目录与常见安装位置",
        "ls -la /home/lighthouse 2>/dev/null || true; echo ----; find /home/lighthouse -maxdepth 3 \\( -iname '*hermes*' -o -iname '*agent*' \\) 2>/dev/null | head -n 200; echo ----; find /opt /usr/local /etc/systemd/system /lib/systemd/system -maxdepth 3 \\( -iname '*hermes*' -o -iname '*agent*' \\) 2>/dev/null | head -n 200",
    ),
    (
        "agentuser 安装目录与启动线索",
        "ps -o user,pid,ppid,cmd -p 3914 || true; echo ----; ls -la /home/agentuser 2>/dev/null || true; echo ----; ls -la /home/agentuser/.hermes 2>/dev/null || true; echo ----; find /home/agentuser/.hermes -maxdepth 3 -type f 2>/dev/null | head -n 120; echo ----; grep -R -nE 'hermes|agentuser' /etc/systemd/system /lib/systemd/system 2>/dev/null | head -n 120; echo ----; crontab -l -u agentuser 2>/dev/null || true; echo ----; crontab -l -u root 2>/dev/null || true",
    ),
]

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(hostname=HOST, username=USER, password=PASSWORD, timeout=10, banner_timeout=10, auth_timeout=10)

for title, cmd in CMDS:
    stdin, stdout, stderr = client.exec_command(cmd, timeout=120)
    out = stdout.read().decode("utf-8", "ignore")
    err = stderr.read().decode("utf-8", "ignore")
    print(f"\n===== {title} =====")
    print(out.strip())
    if err.strip():
        print(f"[stderr] {err.strip()}")

client.close()
