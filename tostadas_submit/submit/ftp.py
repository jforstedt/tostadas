import os
import logging
import ftplib
from abc import ABC, abstractmethod

import paramiko


class TransferClient(ABC):
    @abstractmethod
    def connect(self):
        pass

    @abstractmethod
    def make_dir(self, dir_path):
        pass

    @abstractmethod
    def change_dir(self, dir_path):
        pass

    @abstractmethod
    def upload_file(self, local_path, remote_name):
        pass

    @abstractmethod
    def download_file(self, remote_file, local_path):
        pass

    @abstractmethod
    def file_exists(self, file_path):
        pass

    @abstractmethod
    def close(self):
        pass


class FTPTransferClient(TransferClient):
    """Port of FTPClient from submission_helper.py lines 613-686."""

    def __init__(self, config_dict):
        self.host = config_dict.get("NCBI_ftp_host", "ftp-private.ncbi.nlm.nih.gov")
        self.username = config_dict.get("NCBI_username", "")
        self.password = config_dict.get("NCBI_password", "")
        self.ftp = None

    def connect(self):
        self.ftp = ftplib.FTP(self.host)
        self.ftp.login(user=self.username, passwd=self.password)
        logging.info(f"Connected to FTP {self.host}")

    def make_dir(self, dir_path):
        parts = dir_path.strip("/").split("/")
        current = ""
        for part in parts:
            current = f"{current}/{part}"
            try:
                self.ftp.mkd(current)
            except ftplib.error_perm:
                pass  # directory may already exist

    def change_dir(self, dir_path):
        self.ftp.cwd(dir_path)
        logging.info(f"Changed to directory: {dir_path}")

    def file_exists(self, file_path):
        try:
            self.ftp.size(file_path)
            return True
        except ftplib.error_perm:
            return False

    def download_file(self, remote_file, local_path):
        with open(local_path, "wb") as f:
            self.ftp.retrbinary(f"RETR {remote_file}", f.write)

    def upload_file(self, local_path, remote_name):
        with open(local_path, "rb") as f:
            self.ftp.storbinary(f"STOR {remote_name}", f)
        logging.info(f"Uploaded {local_path} -> {remote_name}")

    def close(self):
        if self.ftp:
            try:
                self.ftp.quit()
            except Exception:
                self.ftp.close()


class SFTPTransferClient(TransferClient):
    """Port of SFTPClient from submission_helper.py lines 548-611."""

    def __init__(self, config_dict):
        self.host = config_dict.get("NCBI_sftp_host", "sftp-private.ncbi.nlm.nih.gov")
        self.username = config_dict.get("NCBI_username", "")
        self.password = config_dict.get("NCBI_password", "")
        self.ssh = None
        self.sftp = None

    def connect(self):
        self.ssh = paramiko.SSHClient()
        self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.ssh.connect(self.host, username=self.username, password=self.password)
        self.sftp = self.ssh.open_sftp()
        logging.info(f"Connected to SFTP {self.host}")

    def make_dir(self, dir_path):
        parts = dir_path.strip("/").split("/")
        current = ""
        for part in parts:
            current = f"{current}/{part}"
            try:
                self.sftp.stat(current)
            except FileNotFoundError:
                self.sftp.mkdir(current)

    def change_dir(self, dir_path):
        self.sftp.chdir(dir_path)
        logging.info(f"Changed to directory: {dir_path}")

    def file_exists(self, file_path):
        try:
            self.sftp.stat(file_path)
            return True
        except FileNotFoundError:
            return False

    def download_file(self, remote_file, local_path):
        self.sftp.get(remote_file, local_path)

    def upload_file(self, local_path, remote_name):
        self.sftp.put(local_path, remote_name)
        logging.info(f"Uploaded {local_path} -> {remote_name}")

    def close(self):
        if self.sftp:
            self.sftp.close()
        if self.ssh:
            self.ssh.close()


class DryRunClient(TransferClient):
    """Logs all operations without making network connections."""

    def __init__(self, config_dict):
        self.host = config_dict.get("NCBI_ftp_host", "ftp-private.ncbi.nlm.nih.gov")

    def connect(self):
        logging.info(f"[DRY-RUN] Would connect to {self.host}")

    def make_dir(self, dir_path):
        logging.info(f"[DRY-RUN] Would create directory: {dir_path}")

    def change_dir(self, dir_path):
        logging.info(f"[DRY-RUN] Would change to: {dir_path}")

    def file_exists(self, file_path):
        logging.info(f"[DRY-RUN] Would check if exists: {file_path}")
        return False

    def download_file(self, remote_file, local_path):
        logging.info(f"[DRY-RUN] Would download {remote_file} -> {local_path}")

    def upload_file(self, local_path, remote_name):
        logging.info(f"[DRY-RUN] Would upload {local_path} -> {remote_name}")

    def close(self):
        logging.info("[DRY-RUN] Would close connection")


def get_client(config_dict, mode="ftp", dry_run=False):
    if dry_run:
        return DryRunClient(config_dict)
    if mode == "sftp":
        return SFTPTransferClient(config_dict)
    return FTPTransferClient(config_dict)
