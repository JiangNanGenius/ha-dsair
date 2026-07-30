# DS-AIR 1.3.20 / AC Master V58 上线记录

日期：2026-07-20

## 结论

- 大金 `清爽`、`睡眠`、`自动除湿`、`强力除湿` 等仍按原厂独立工作模式处理，
  不降格成普通制冷状态，也不伪造成湿度百分比。
- Home Assistant 2026.7 的 `climate.set_hvac_mode` 会通过
  `vol.Coerce(HVACMode)` 限制为核心固定枚举；直接加入自定义模式会导致服务
  调用校验失败。生产方案继续使用精确的 DS-AIR 工作模式 select，但把它和
  原生 climate 放进同一张仪表板卡片，用户界面统一显示为“工作模式”。
- 默认仪表板中的 10 张中弘温控卡全部替换成原生 DS-AIR climate；页面中不再
  存在中弘实体引用或标题。
- AC Master 升级到 V58：中弘 TCP 接收、发送、状态轮询、MQTT 发布、命令翻译
  等 28 个节点保留原位置并标记为 `[已封存·中弘]`，同时全部禁用。
- AC Master 活动 HA 事件订阅移除了 10 个中弘 climate，加入 10 个 DS-AIR
  精确工作模式和 10 个原生回风温度实体。中弘不再参与查询、刷新、模式判断、
  温度补偿或控制。
- 科力屋协议页的混合温度桥并非中弘专用，因此没有整节点停用；其中唯一的中弘
  二楼中厅来源和触发实体已替换为
  `sensor.ds_air_room_6_inlet_temperature`。最终所有启用页、启用节点中，中弘引用
  数量为 0。
- 当前 10 个 DS-AIR 原生回风温度实体仍为 `unavailable`。V58 对这项证据明确
  失败关闭，不再回退中弘，因此相关温差补偿会显示无回风温度证据。

## 同轮根因修复

AC Master V57/V58 的温度命令确认分支曾错误引用水阀代码中的未定义变量
`feedbackSeq`，在物理设定温度确认后导致周期性 `ReferenceError`。现已改为记录
DS-AIR 目标温度物理坐标 `physical.generation`。热修复重启后的日志窗口没有再次
出现 V58、`feedbackSeq` 或 `ReferenceError`。

## 验证

- DS-AIR：`60 passed`，相关 Python 文件 `py_compile` 通过。
- Node-RED：1069 个 Function 节点全部通过 JavaScript 编译检查。
- 中弘封存：28 个节点 `d=true`；活动事件订阅中中弘实体数为 0；
  `192.168.20.7:9999` 活动 TCP 节点数为 0。
- 大金事件：精确工作模式 10 个，原生回风温度 10 个。
- Lovelace：中弘实体引用 0，中弘文字 0；原生大金 climate 10 个，工作模式
  select 10 个。
- 线上容器：`homeassistant` 正常运行；`mynodered` healthy。

## 线上校验值与备份

- Node-RED V58 最终 SHA-256：
  `6dbefbaad11f1eb0246f65bd6eff95df262720a7aecee3858d1fb6fc2c95dd0f`
- Lovelace SHA-256：
  `4e6e4d4529fde3ff1157623b8278d3dde614a4f8f47700a6b38c24665b5904b9`
- DS-AIR 1.3.20 部署包 SHA-256：
  `335dfc6347588d598ec3393dfbca4462010ed07a1ee2b1671547a5029fd5ea6d`
- 流备份：
  `/usr/share/hassio/homeassistant/Node_red_files/backups/flows-before-ac-v58-20260720T174245.json`
- 温度确认热修复前流备份：
  `/usr/share/hassio/homeassistant/Node_red_files/backups/flows-before-ac-v58-temp-ack-20260720T174630.json`
- 混合温度桥原生化前流备份：
  `/usr/share/hassio/homeassistant/Node_red_files/backups/flows-before-ac-v58-mixed-source-20260720T175120.json`
- 仪表板备份：
  `/usr/share/hassio/homeassistant/backups/lovelace-before-daikin-native-20260720T174245.json`
- DS-AIR 备份：
  `/usr/share/hassio/homeassistant/backups/ds-air-before-1.3.20-20260720T174245`
