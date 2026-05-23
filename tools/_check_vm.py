import paramiko

HOST = "192.168.200.33"
USER = "gslab"
PASS = "qqq123"

def run(ssh, cmd, timeout=30):
    _, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode()
    err = stderr.read().decode()
    rc = stdout.channel.recv_exit_status()
    return rc, out, err

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASS, timeout=15)

rc, out, err = run(ssh, "cat /home/gslab/extract_zip.py")
print("extract_zip.py:")
print(out)

rc, out, err = run(ssh, "ls /home/gslab/*.zip 2>/dev/null")
print("ZIPs:", out.strip())

ssh.close()
