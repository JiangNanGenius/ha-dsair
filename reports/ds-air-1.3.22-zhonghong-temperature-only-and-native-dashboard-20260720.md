# DS-AIR 1.3.22 / AC Master V61 上线记录

日期：2026-07-20

## 结论

- 大金原生 `climate` 继续作为唯一空调控制权威。
- 中弘能力缩减为“只读缺失的回风温度”：插件维持一条到
  `192.168.20.7:9999` 的只读 TCP 会话，只发送完整校验的查询
  `01 50 FF FF FF FF 4D`，只接受校验和正确的 `0x50` 状态记录，并且只解析
  每条记录的第 7 字节（索引 6）作为回风温度。
- 中弘记录中的设定温度、工作模式、风速、风向和能力位均被忽略；插件不会创建
  中弘 climate、select、fan 或其他控制实体，也不会发送中弘控制指令。
- 房间映射为 DS-AIR `room_id -> 中弘 indoor_address = room_id - 1`，外机地址为 1。
  有效观测写入原生大金 climate 的 `current_temperature`，并用
  `ds_air_current_temperature_source_role=zhonghong_temperature_only` 标明来源。
- 温度证据 120 秒超时后失败关闭；若用户显式绑定了其他 HA 回风温度实体，显式
  绑定优先于内置中弘只读观测。

## 原生 Home Assistant 面板

- 默认仪表板的 10 台目标内机均使用原生 `thermostat` 卡片。
- HVAC、风速、摆风和扩展工作模式在同一张原生 climate 卡片中操作；清爽、自动
  除湿、睡眠等扩展模式通过预设模式入口呈现，精确工作模式实体继续保留供自动化
  和诊断使用。
- 仪表板中没有中弘实体引用或中弘文字，回风温度直接显示为原生 climate 当前温度。

## 制热能力处理

- 现场 D611 返回的原始能力字节未声明制热，但实际系统已确认支持制热。
- 1.3.22 使用显式 `force_heat_mode` 配置覆盖，不篡改原始解码结果；实体同时暴露
  `ds_air_gateway_heat_capability=false`、
  `ds_air_effective_heat_capability=true` 和
  `ds_air_heat_capability_source=configured_override`，便于追溯。
- 部署和验证过程没有发送制热或其他空调控制命令。

## Node-RED

- AC Master 升级到 V61，只从原生大金 climate 的属性消费回风温度和来源证据，
  不直接订阅 `climate.zhonghong_hvac_*`。
- V61 修复了批量 HA 状态刷新遗漏温度来源属性、进而擦除实时回风温度的问题。
- 原 AC Master Tab 内 28 个中弘 TCP、MQTT、命令和状态节点保留作为档案，均使用
  Node-RED 实际禁用字段 `d=true`；没有重新启用旧中弘流。
- 三个历史中央空调 Tab 继续以 `disabled=true` 整页封存；此外，全部 10 个指向
  `192.168.20.7:9999` 的历史 TCP 输入/输出节点也逐个设为 `d=true`。重启后进程
  归属检查确认唯一剩余连接属于 Home Assistant 的 `python3` 温度观察器，Node-RED
  不再拥有中弘 TCP 连接。

## 验证

- 本地测试：`67 passed`。
- HA 线上：10/10 台原生大金 climate 均取得有效回风温度，来源均为
  `zhonghong_readonly://192.168.20.7:9999/1/<indoor_address>`。
- HA 线上：10/10 台 climate 均显示制热能力；原始能力位和显式覆盖来源保持可见。
- AC Master：`sensor.ac_master_diagnostics` 显示算法版本
  `2026-07-20.ac-dsair-temperature-hydration-v61`，10/10 个房间的
  `return_temp` 均非空。
- Lovelace：10 张原生 thermostat 卡，中弘引用为 0。
- 旧中弘 MQTT climate 在注册表/状态机中仍有 10 个历史对象，但 10/10 均为
  `unavailable`，可用活动对象为 0；这些残留不再构成控制或数据源。
- 最终日志窗口没有新增 DS-AIR、中弘温度观察器或 AC Master 错误。

## 备份

- DS-AIR 1.3.22 部署前：
  `/usr/share/hassio/homeassistant/backups/ds-air-before-1.3.22-20260720-182603`
- DS-AIR 1.3.22 线上目录部署前：
  `/usr/share/hassio/homeassistant/backups/ds-air-live-before-1.3.22-20260720-182603`
- Lovelace 原生大金面板部署前：
  `/usr/share/hassio/homeassistant/backups/lovelace.lovelace-before-native-daikin-20260720-183104.json`
- Node-RED AC Master V60 前：
  `/usr/share/hassio/homeassistant/Node_red_files/flows.before-acmaster-v60-20260720-183321.json`
- Node-RED AC Master V61 前：
  `/usr/share/hassio/homeassistant/Node_red_files/flows.before-acmaster-v61-20260720-183734.json`
- Node-RED 历史中弘 TCP 节点硬隔离前：
  `/usr/share/hassio/homeassistant/Node_red_files/flows.before-zhonghong-transport-retirement-v62-20260720-184629.json`
