import paramiko

HOST = "192.168.200.33"
USER = "gslab"
PASS = "qqq123"
LOCAL = r"C:\Users\gslab\Documents\New project\form-system-kit-composer\dist\client-deploy-mvp-import-flow.zip"
REMOTE = "/home/gslab/client-deploy-mvp-import-flow-v12.zip"

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASS, timeout=15)

sftp = ssh.open_sftp()
print("Uploading...")
sftp.put(LOCAL, REMOTE)
sftp.close()
print("Upload done:", REMOTE)
ssh.close()
