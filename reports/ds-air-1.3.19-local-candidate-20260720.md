# DS-AIR 1.3.19 本地候选说明

日期：2026-07-20

状态：**已部署到 Home Assistant 生产环境，hotfix2**

## 本轮收紧

- 设定温度不再乐观修改共享状态；增加独立的 target physical
  `epoch/generation/observed_at/source/value`，并在命令后定向查询网关状态。
- 外部绑定的温湿度只接受有限数值；`unknown`/`unavailable`/实体删除会立即
  清空旧值，并公开来源实体和最后有效观测时间。
- `hvac_action` 只保留可证明的 `OFF`；在没有压缩机/盘管运行遥测时，开机
  状态不伪造 `COOLING`/`HEATING`。热工作模式家族改由 `ds_air_mode_family`
  独立表达。
- 睡眠模式没有新鲜的外机冷热证据时，HA 兼容投影固定为 `auto`；精确
  select 仍保留 `sleep`。
- 移除错误的 HA 百分比 `TARGET_HUMIDITY` 能力。原生 `0–3` 是未完成能力验证的
  档位枚举，不是相对湿度；1.3.19 暂时 fail-closed，不发送该控制。
- 增加 DTA117D611 明确 profile，锁定已实机验证的解析布局；通用 ACK 不能再
  翻转 D611 解析方式，B/C profile 也最多只接受首个协议 ACK。
- TCP `recv()==b""` 现在被视为连接关闭，立即关闭旧 socket、清理半帧并退避
  重连，不再等待偶然的后续发送失败。
- 风向 select、卫生间换气 select 和新风 fan 不再在网关物理回报前乐观修改
  共享状态；重连后的新 TCP 会话会先发送握手帧，再重放业务包。
- 修复启动诊断查询中的变量名冲突：`GatewaySignalQueryParam` 的业务目标不再
  覆盖 BaseBean 的 `EnumDevice.SYSTEM` 目标。

## cmd243 已知但本轮延后的缺口

1. 当前仍在启动时发送一次 cmd243，然后每 60 秒发送；D611 `03.19.00`
   已证明只回通用 ACK，因此该周期请求尚缺退避。
2. 尚未建立按请求 ID 关联的 10 秒数据等待窗口，也没有
   `unknown/probing/supported/ack_only` 诊断状态。
3. 未来能力状态必须把回风温度和回风湿度分开：湿度缺失不能阻止仅温度
   数据被判定为 `supported`。
4. 建议的最小后续方案是：连续三次匹配 ACK-only 后标记网关级 `ack_only`，
   降为重连、固件版本变化或每日低频探测，并在网关诊断实体公开最后探测
   时间和结果。

当前决策：回风湿度没有生产消费者，预期不可读，不作为中弘封存的
硬门槛；回风温度仍是必须迁移的数据。

## 本地验证

- `python3 -m pytest -q tests`：60 项通过。
- `py_compile`：`param.py`、`service.py`、`select.py`、`fan.py` 通过。

## 生产部署记录

- Node-RED AC Master V57 已部署，线上 flow SHA：
  `249b90cae0809a1458456a1c5cd463e1fbb17f879f476098f76d05d6cd969619`。
- V57 只改动 AC Master 主函数节点 `7b50b58298488ba8` 和中弘 MQTT 命令入口
  `377fd4218dec1743`；中弘命令入口已禁用并断开输出，读温度兜底链暂时保留。
- DS-Air hotfix2 包 SHA：
  `695e302fdee5aabc4d9d3bd8d4c1ead81cc6a260b7921a3a1b77b4265bc8d956`。
- 线上备份：
  `/usr/share/hassio/homeassistant/Node_red_files/backups/flows-before-ac-v57-20260720T171409.json`
  `/usr/share/hassio/homeassistant/backups/ds-air-before-1.3.19-20260720T171409`
  `/usr/share/hassio/homeassistant/backups/ds-air-before-1.3.19-hotfix1-20260720T171606`
  `/usr/share/hassio/homeassistant/backups/ds-air-before-1.3.19-hotfix2-20260720T171944`
- 线上验证：HA/Node-RED 容器健康；`climate.can_ting`、`climate.shu_fang`、
  `climate.ke_ting` 和 `select.ds_air_5_0_native_work_mode` 等原生模式实体已恢复；
  最近日志无 ds_air traceback。残留的充电桩 MQTT number 和若干旧实体缺失提示与本次
  DS-Air/AC Master 变更无关。
