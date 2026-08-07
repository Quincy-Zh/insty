"""VISA 仪器通信基类"""

from __future__ import annotations

import logging
from typing import Optional

from pyvisa.resources import Resource

logger = logging.getLogger(__name__)


class VisaBasedInstrument:
    """基于 VISA 通信协议的仪器基类（混入类）"""

    def __init__(self, resource: Optional[Resource]) -> None:
        """初始化 VISA 仪器"""
        self.visa_inst = resource

    def close(self) -> None:
        """关闭 VISA 连接"""
        if self.visa_inst is not None:
            try:
                self.visa_inst.close()
            except Exception as ex:
                logger.warning(f"Error closing VISA connection: {ex}")

    def run_cmds(self, cmds: list[str]) -> bool:
        """执行一组 SCPI 命令（低层命令批量发送）

        Args:
            cmds: SCPI 命令列表

        Returns:
            全部执行成功返回 True，否则返回 False
        """
        for cmd in cmds:
            try:
                self.visa_inst.write(cmd.strip())  # type: ignore
                logger.debug(f'Write: "{cmd}"')
            except Exception as ex:
                logger.error(f'Fail to execute command "{cmd}": {ex}')
                return False
        return True

    def query(self, cmd: str) -> Optional[str]:
        """查询命令并返回响应"""
        try:
            resp = self.visa_inst.query(cmd).strip()  # type: ignore
            logger.debug(f'QUERY: "{cmd}" -> "{resp}"')
            return resp
        except Exception as ex:
            logger.error(f'Fail to query command "{cmd}": {ex}')
            return None


# 导入所有驱动模块以触发注册
from .drivers import (  # noqa: F401
    agilent_33512b,
    agilent_33519,
    agilent_53220a,
    itech_it6302,
    keithley_dmm6500,
    temptronic_ats_710,
    zhiyuan_zds1000,
)
