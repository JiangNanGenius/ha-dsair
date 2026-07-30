# ds_air 1.3.16 与 AC Master V54：二楼卧室三风速实机修复

日期：2026-07-17

## 结论

二楼卧室三已从异常 `AUTO` 收敛到 AC Master 要求的 `HIGH`，并由大金原生网关状态帧完成
物理确认。最终控制链是：

`AC Master -> climate.er_lou_wo_shi_san -> ds_air -> 大金原生网关 -> room 5/unit 0`

中宏 `climate.zhonghong_hvac_1_4` 只保留为温度和运行细节的补充证据，不是命令目标。

## 根因

AC Master V53 的 `applyPanelRecoveryHolds()` 在科力屋面板快照暂时不可用或恢复中时，会清空
`bedroom3_sync_fan`。这会在链路抖动时短暂交还风速控制权，使已经接管的内机回到 AUTO。
2026-07-17 10:49:59 的 HIGH -> AUTO 正发生在面板快照抖动和异常温度跳变窗口；HA recorder
没有对应的卧室三风速服务调用，排除了正常 Node-RED/HA 命令写入。旧 V4.1 节点所在整页已
禁用，也不是在线竞争写入者。

## AC Master V54

- 面板恢复期间保留 `sync_fan`，不再因快照暂缺而放弃原生内机风速接管；
- 每次发送记录物理 epoch、generation、观察时间和 attempt；
- 只接受同 epoch 且 generation 递增的 ds_air 网关状态为物理 ACK；
- 25 秒确认窗口后仍不匹配就继续重试，不设置低次数上限；
- generic `SYS_ACK` 只证明网关收到命令，不视为内机已执行。

V54 已合并在线上完整 Node-RED flow，SHA-256 为
`b1ca147db60375c22c1f0439310aaad531c9966bcbe4f746945789b68cf1f2d2`。

## ds_air 1.3.16

反编译大金官方 App 后确认，风速命令采用 `AIR_FLOW-only`：

- target：`08:17`；
- room/unit：`05 00`；
- flag：`04`；
- HIGH：`04`；
- body：`05 00 04 04`。

因此 1.3.16 使用官方单字段语义，不保留试验性的 `0x07/0x17` 组合字段。集成同时保留：

- 命令发送后不乐观修改 HA 状态；
- 1/3/8/15/25 秒定向查询；
- `ds_air_fan_physical_epoch/generation/mode/source/observed_at_ms` 属性；
- 只有真实网关状态才能推进 physical generation。

## 实机闭环

第一次故障收敛：

- 20:33:42、20:34:08、20:34:34 的前三次 HIGH 均未得到 HIGH 物理状态；
- 20:35:00 发送第 4 次；
- 20:35:14 收到 room 5 `STATUS_CHANGED ... 05 00 04 04`；
- 20:35:15 定向查询确认 HIGH；
- 20:35:17 AC Master 记录 attempt 4 的物理 ACK，pending 清空。

1.3.16 部署重启后的官方语义复核：

- 20:50:33 发送 `... 08 17 ... 05 00 04 04 ...`；
- 1 秒、3 秒、8 秒定向查询均返回 room 5 HIGH；
- 20:56 后 HA 原生实体与 Node-RED 再次确认：
  `fan_mode=high`、`ds_air_fan_physical_mode=high`、epoch
  `e145b4f990874be69002a6af02db48fd`、generation `7`、
  `bedroom3_sync_fan=high`、`bedroom3_fan_command_pending=null`。
- 21:02 最终复核时 physical generation 已继续推进到 `8`，模式仍为 HIGH。

重启后的命令是在已为 HIGH 的状态上做无回退验证；真正的 AUTO -> HIGH 转换证据是 20:35
第 4 次发送及随后独立到达的状态帧。

## 部署与测试

- `climate.py` 本地/线上 SHA-256：
  `d951afcc0de204cf1eccd02aacd8166117d12ebb4ef9d08b24db1e1837c03386`；
- `manifest.json` 本地/线上 SHA-256：
  `a5f6f3be570ed7f7776c1928599a7623cd740f894762d3e6117b2b64bb50c2d7`；
- 版本：`1.3.16`；
- `python3 -m pytest -q ha-dsair/tests`：33 项通过；
- Node-RED V54/V41 组合测试：623 个启用 Function 全部编译并通过物理 ACK、epoch 重置和持续
  重试反例；
- 最终备份：
  `/usr/share/hassio/homeassistant/.codex-backups/ds-air-1.3.15-before-official-airflow-v1316-20260717-2051`。

最终判断：**卧室三风速控制已完成协议、控制权和物理确认三层修复，线上状态 PASS。**
