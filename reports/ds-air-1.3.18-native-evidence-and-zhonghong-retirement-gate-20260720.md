# DS-AIR 1.3.18 原生能力生产证据与中弘封存门槛

日期：2026-07-20

取证窗口：15:30 起，含 16:00–16:05 Node-RED V56 部署、冷启动修复与复核

结论状态：**DS-AIR 1.3.18 与 AC Master V56 已上线；中弘当前不可封存**

## 1. 结论

本轮已经证明，大金原生 `ds_air` 可以作为 10 台内机的唯一命令权威，并可直接提供：

- 真实开关状态、精确原生工作模式、目标温度；
- 普通内机的 1–5 档风速和自动档；
- 厨房、二楼大卫生间两档机的低/高两档风速；
- `清爽`、`睡眠`、`自动除湿`、`强力除湿` 等独立原生模式的能力和当前状态；
- 由网关状态帧推进的 power、mode、fan 物理证据坐标，而不是本地乐观回显。

AC Master V56 也已部署到生产：10 个原生房间以 `ds_air` 精确属性、原生模式 select 和真实
风速 profile 为权威输入。首次冷启动暴露的未水合误写已从根因修复，最终冷启动回归为零 service
call；生产 Node-RED 再次重启后没有重现无效空调服务调用。

但本轮也证明，当前 DTA117D611 对官方 App 使用的 cmd243 回风温湿度查询只返回通用
`SYS_ACK`，没有返回携带房间温湿度 TLV 的 cmd243 数据帧。因此 10 个房间的原生回风温度、
回风湿度实体均正确保持 `unavailable`，原生 `climate` 的 `current_temperature` 也保持
`null`，没有把保留字节伪装成温度。

所以当前架构应保持：

> 大金原生是唯一控制权威；中弘仅作为回风温度等缺失数据的只读补充证据和最后兜底。

只有满足第 8 节全部退出门槛后，才可以封存中弘。封存应采用“备份后禁用、观察、归档”，
而不是直接删除。

## 2. 本报告边界

- 本报告只记录本轮已经取得的生产证据，不把协议推测写成设备能力。
- 本轮已部署的是 Home Assistant 自定义集成 DS-AIR 1.3.18。
- Node-RED AC Master V56 已完成备份、部署、首次冷启动问题修复及最终线上重启验证。
- 本报告没有记录 Home Assistant token、密码、认证头或其他敏感值。
- 本报告更新后，最终生产 flow 已机械同步到本地 private 真相仓库；同步没有再次修改线上状态，
  也没有触碰 sanitized 仓库。

## 3. 1.3.18 部署与回退证据

线上组件：

- 运行路径：`/usr/share/hassio/homeassistant/custom_components/ds_air`
- 部署 staging：`/usr/share/hassio/homeassistant/.codex-staging/ds-air-1.3.18-20260720`
- 线上 `manifest.json` 版本：`1.3.18`

部署前及物理证据测试前备份：

| 用途 | 线上路径 | SHA-256 |
| --- | --- | --- |
| 1.3.18 部署前完整组件备份 | `/usr/share/hassio/homeassistant/backups/ds-air-before-1.3.18-20260720T1530.tgz` | `9151bab0b0689999563c0e6b4de58afe77adc700e67a82966b1000be2fce2607` |
| power/mode 物理证据改动前的 `climate.py` | `/usr/share/hassio/homeassistant/backups/ds-air-climate-before-physical-evidence-20260720T1545.py` | `576b016cf424592940d72ad1b92ffdead5c93ab06bd06ee93050fc405a8d390d` |

本轮只读核验的部分线上文件校验值：

| 文件 | SHA-256 |
| --- | --- |
| `climate.py` | `f312cdabec8478e8326520475efa6bc54fabce9de1f9b9052fd22d9102c76dba` |
| `select.py` | `e11dbc27ae7cf1da9b6ef7db31944c32c40b489402160aa22ca438099254bf96` |
| `manifest.json` | `cd99fc875fe8795d6f94de80c4ab7d552dad80dbcbb74148a3bff969156f32f6` |

本地回归测试在 2026-07-20 15:50 CST 运行 `python3 -m pytest -q tests`，结果为
**50 项通过**。这证明当前工作区协议/实体回归集通过，但不能替代下述真实网关和 HA 实体证据。

相关实现与测试路径：

- `ha-dsair/custom_components/ds_air/climate.py`
- `ha-dsair/custom_components/ds_air/select.py`
- `ha-dsair/custom_components/ds_air/sensor.py`
- `ha-dsair/custom_components/ds_air/ds_air_service/param.py`
- `ha-dsair/custom_components/ds_air/ds_air_service/decoder.py`
- `ha-dsair/custom_components/ds_air/ds_air_service/service.py`
- `ha-dsair/tests/test_climate_partial_status.py`
- `ha-dsair/tests/test_aircon_query_status_decoder.py`
- `ha-dsair/tests/test_protocol_diagnostics.py`

## 4. 10 房原生模式与风速生产快照

下表来自部署后的 Home Assistant API 只读快照。模式和能力由大金网关状态/能力包产生，
没有用中弘状态反推。普通 `climate` 为兼容 HA 标准模式会投影部分状态；精确语义以对应的
`select.ds_air_<room>_0_native_work_mode` 和 `ds_air_native_mode*` 属性为准。

| room | 房间 / 原生 climate | 精确模式快照 | 原生模式能力 | 风速能力 |
| --- | --- | --- | --- | --- |
| 1 | 厨房 / `climate.chu_fang` | 制冷 | 制冷、送风 | 两档：`low`、`high` |
| 2 | 二楼大卫生间 / `climate.er_lou_da_wei_sheng_jian` | 送风 | 制冷、送风、强力除湿 | 两档：`low`、`high` |
| 3 | 餐厅 / `climate.can_ting` | 制冷 | 制冷、送风、自动除湿、清爽、睡眠 | 五档：`1`–`5`，另有 `auto` |
| 4 | 书房 / `climate.shu_fang` | 制冷 | 制冷、送风、自动除湿、清爽、睡眠 | 五档：`1`–`5`，另有 `auto` |
| 5 | 二楼卧室三 / `climate.er_lou_wo_shi_san` | 清爽 | 制冷、送风、自动除湿、清爽、睡眠 | 五档：`1`–`5`，另有 `auto` |
| 6 | 二楼中厅 / `climate.er_lou_zhong_ting` | 制冷 | 制冷、送风、自动除湿、清爽、睡眠 | 五档：`1`–`5`，另有 `auto` |
| 7 | 客厅 / `climate.ke_ting` | 制冷 | 制冷、送风、自动除湿、清爽、睡眠 | 五档：`1`–`5`，另有 `auto` |
| 9 | 一楼卧室 / `climate.yi_lou_wo_shi` | 清爽 | 制冷、送风、自动除湿、清爽、睡眠 | 五档：`1`–`5`，另有 `auto` |
| 10 | 二楼卧室一 / `climate.er_lou_wo_shi_yi` | 制冷 | 制冷、送风、自动除湿、清爽、睡眠 | 五档：`1`–`5`，另有 `auto` |
| 11 | 二楼卧室二 / `climate.er_lou_wo_shi_er` | 制冷 | 制冷、送风、自动除湿、清爽、睡眠 | 五档：`1`–`5`，另有 `auto` |

对应的 10 个精确模式实体均已注册并返回状态：

`select.ds_air_1_0_native_work_mode`、`select.ds_air_2_0_native_work_mode`、
`select.ds_air_3_0_native_work_mode`、`select.ds_air_4_0_native_work_mode`、
`select.ds_air_5_0_native_work_mode`、`select.ds_air_6_0_native_work_mode`、
`select.ds_air_7_0_native_work_mode`、`select.ds_air_9_0_native_work_mode`、
`select.ds_air_10_0_native_work_mode`、`select.ds_air_11_0_native_work_mode`。

## 5. 模式语义与物理确认边界

### 5.1 清爽不是子模式

`清爽` 是大金原生独立工作模式，原始代码为 `6`，稳定键为 `comfort`。它属于制冷家族，
配合机组自身的自动除湿能力工作；在 HA 标准 `climate` 上兼容投影为 `cool`，但精确 select
和属性始终保留 `清爽/comfort/6`，不能降格成 preset 或普通制冷的布尔子开关。

清爽模式仍允许人工风速控制。相反，除湿、自动除湿、睡眠、预热、强力除湿由原厂逻辑接管
风速时，集成不应持续写风速。这一点是修复清爽阶段风速频繁跳变的协议前提。

`睡眠` 同样是独立工作模式，不是 preset。HA 没有对应的标准独立模式，因此兼容层依据原生
外机冷热条件投影为 `cool` 或 `heat`；条件不明确时使用保守的 `auto`，精确 select 仍显示
`睡眠`。卫生间的换气弱/强才属于设备子功能，不应与独立工作模式混淆。

### 5.2 power、mode、fan 使用独立物理证据坐标

`climate.py` 为状态实例提供运行期 epoch，并分别维护：

- `ds_air_power_physical_generation/observed_at_ms/source/value`
- `ds_air_mode_physical_generation/observed_at_ms/source/key/code`
- `ds_air_fan_physical_epoch/generation/observed_at_ms/source/mode`

power 与 mode 的 generation 分开推进，避免只更新模式的部分状态包把旧开关状态伪装成新证据，
反之亦然。本地 HA service call 不推进这些坐标；只有网关 `STATUS_CHANGED` 或定向
`QUERY_STATUS` 返回才推进。

本轮实机日志中，15:43:56 对 room 5 发出控制后先收到通用 ACK，15:43:58 另行收到
`AirConStatusChangedResult`，其中 `switch=ON`、`mode=RELAX`；15:44:06 对 room 11 发出
控制后先收到通用 ACK，15:44:09 另行收到 `AirConStatusChangedResult`，其中
`switch=ON`、`mode=COLD`。这证明 ACK 与物理状态确认是两件事，也证明 power/mode 坐标可以
由真实网关状态分别落证。

必须继续遵守：

- 通用 `SYS_ACK` 只说明网关接收了请求，不能作为内机已执行的物理 ACK；
- ACK body 的 `0x02` 不能被当成错误码；是否成功执行要看后续权威状态帧和物理坐标；
- `hvac_action` 是由开关、精确模式和外机冷热条件做出的 HA 兼容投影，**不是压缩机实际运行、
  压缩机频率、电子膨胀阀、盘管温度或冷媒状态的证据**。

## 6. cmd243：协议实现正确，但当前网关没有返回数据

集成按官方 App 的格式每 60 秒发送一次 room-scoped inlet temperature/humidity 查询：

```text
02 11 00 0d 00 00 00 <cnt> 00 00 00 00 00 00 00 00 01 f3 00 ff 03
```

其中 `subbody_ver=0`、命令 `f3 00` 即十进制 243，`ff` 表示查询全部房间。本轮连续日志样本：

```text
15:42:40.828 send  0211000d00000047000000000000000001f300ff03
15:42:40.868 recv  0211000d0000004700000000000000000001000203

15:43:40.830 send  0211000d00000049000000000000000001f300ff03
15:43:40.867 recv  0211000d0000004900000000000000000001000203
```

接收帧与请求计数 `0x47`、`0x49` 匹配，但解码结果均为
`AckResult(target=SYSTEM, cmd_type=SYS_ACK, subbody_ver=0)`，只有 ACK body `0x02`；没有出现
cmd243 数据响应，也没有任何房间温度/湿度 TLV。因此当前结论只能是：

1. DTA117D611 收到了官方格式请求；
2. 此网关/当前协议端点没有向本会话返回 cmd243 温湿度数据；
3. `0x02` 是通用 ACK body，不是可据此判定“命令错误”的错误码；
4. 不能把 ACK、保留字节、目标温度或 `hvac_action` 推导成回风温度。

部署后的 10 个房间温度实体和 10 个湿度实体均存在，但全部为 `unavailable`，例如：

- `sensor.ds_air_room_5_inlet_temperature`
- `sensor.ds_air_room_5_inlet_humidity`
- `sensor.ds_air_room_11_inlet_temperature`
- `sensor.ds_air_room_11_inlet_humidity`

实体采用房间作用域而非虚假的 unit 作用域，并有 180 秒有效期；没有收到完整、有效 TLV 时保持
不可用，旧值超过有效期也会回到不可用。这是安全行为，不是需要用猜测值“修复”的 UI 问题。

### 6.1 官方 App 其他命令的替代能力审计

对官方 App 本地 Socket、DAO、DTO 和 UI 调用链的只读追踪没有找到 cmd243 的可实证替代：

| 命令 | 官方语义 / 已见字段 | 是否能替代所缺数据 |
| --- | --- | --- |
| cmd2/258、cmd3/259 | 开关、精确模式、风量、设定温度、风向、加湿设定、3D 新风；保留 bit3 的 1 字节被官方 App 丢弃 | **不能**；不得猜成回风温度或压缩机状态 |
| cmd60、cmd61 | 挡板实际/设定、凝露保护、外机静音，以及挡板/湿度设定/新制冷/静音能力 | **不能**；没有所需测量值 |
| cmd89 `Sensor2Info` | 独立外置 AirSensor 的温湿度、PM2.5、CO2、VOC/TVOC、HCHO | **不能直接替代**；只属于实际存在的外置传感器，不能冒充内机回风 |
| cmd208 | APK 内有恒温恒湿 DTO/decoder 声明 | **不能**；没有 builder、caller、setter、DB 或 UI 完整调用链，当前只是声明 |
| cmd220 `Daikin Care` | 有完整只读调用链，返回温差、干喉、湿冷、闷热、霉变等 `0`–`2` 派生等级 | **不能**；不是原始温湿度、盘管、蒸发器或压缩机数据，且 D611 实机回包尚未证明 |

APK 中 `AirConDevice.inletTemperature/inletHumidity` 的唯一非 DAO 写入点仍是 cmd243；数据模型和
本地 Socket 路径也没有压缩机、盘管或蒸发器字段。本轮 D611 抓包没有出现上述命令可替代的真实
遥测回包。因此下一步最多可被动记录现有启动/轮询流中的 258/259、60/61、89、208、220，不能
在没有实机数据帧时把 APK 中出现过的字段升级成“支持”。

## 7. AC Master V56 生产状态与中弘依赖审计

生产 Node-RED 流路径：
`/usr/share/hassio/homeassistant/Node_red_files/flows.json`。最终线上 SHA-256 为：

```text
5168b32490fd6f9d541b4fd0120dcfaeef052b5fff5b9d181923a06e8c12b5da
```

本地 private 真相文件
`Node-RED-ControlSystem-HongYeVilla-local-full/ALLFlow.json` 已同步为同一 SHA-256。同步后验证为
4008 个节点、32 个 tab、1069 个 Function 节点、4008 个唯一 ID，全部启用 Function 均可编译；
相对同步前只改动 5 个目标节点并新增 1 个中弘只读能力节点，没有删除节点。同步前本地备份为
`/tmp/ALLFlow.before-ac-v56-local-sync-20260720.json`，SHA-256 为
`6937f930ff527081c86b53d825867703119a9c857700dfbd232d4b93502b1560`。本地仓库原有暂存和
未暂存改动均保留，sanitized 仓库未改动。

Node-RED 回退证据：

| 用途 | 线上路径 |
| --- | --- |
| V56 部署前完整 flow | `/usr/share/hassio/homeassistant/Node_red_files/backups/flows-before-ac-v56-20260720T1600.json` |
| 首次 V56 冷启动修复前 flow | `/usr/share/hassio/homeassistant/Node_red_files/backups/flows-ac-v56-before-coldstart-fix-20260720T1605.json` |

### 7.1 首次冷启动问题及根因修复

V56 首次冷启动时，Node-RED 已开始计算，但 HA WebSocket 状态尚未完成水合。旧兼容探测把
“精确属性/select/profile 尚未知”误判成需要回退，因而尝试发出：

- `set_preset_mode`；
- `set_hvac_mode: auto`；
- 旧五档词汇中的 `high`。

这不是大金协议或实体能力错误，而是冷启动证据门控不完整。最终修复在根因层完成：10 个 native
`ds_air` 房间在 exact attributes、原生模式 select 和 fan profile 完成水合前，一律禁止 legacy
mode/preset/fan 探测和写入。厨房与二楼大卫生间的风速词汇继续固定为静态 `low/high`，不会被
未水合状态误识别成五档机或旧兼容风速。

最终冷启动回归产生 **0 个 service call**。生产 Node-RED 重新启动后只出现 HA WebSocket 建连期
短暂 `NoConnectionError`，连接随后自行恢复；恢复后没有再次出现无效 service call，V56 保持运行。

对 5 号房的追加观察还排除了持续重试风暴：一次已获网关物理确认的风速事务及其定向状态查询结束后，
power/mode 物理 generation 停在 `77`；后续快照 age 已到 `101.1 s` 而 generation 未再增加。
从最终重启恢复点 `16:04:22` 起再次筛查日志，也没有匹配到旧 preset、非法 `hvac_mode:auto`、
旧 `medium/high/稍强` 风速词汇或新的 HA service validation error。

### 7.2 仍存在的中弘只读依赖

当前明确存在的生产依赖：

| 位置 | 节点 | 对中弘的当前依赖 | 封存前动作 |
| --- | --- | --- | --- |
| 空调主控 tab | `7b50b58298488ba8`，AC Master V56 | 原生模式为权威，但在 cmd243 不可用时仍把中弘温度保留为只读最后兜底 | 原生回风温度稳定后移除 fallback，并完成并行观察 |
| 空调主控 tab | `6193594e22d740b8`，HA 状态事件入口 | 为只读补充链监听全部 10 个中弘 climate | 退出门槛满足后移除中弘监听 |
| 科力屋对接协议 tab | `c0fd2bc84a4aa5e8`，中厅温度物理补偿 | 读取 `climate.zhonghong_hvac_1_5` | 换成已验证的新原生回风温度源，或明确取消该补偿 |
| 科力屋对接协议 tab | `936806fd93fa8aa9`，温度补偿触发 | 监听 `climate.zhonghong_hvac_1_5` | 同上 |
| 空调主控 tab | `zhonghong_capability_mqtt_v1`、`76654968dd020b06`、`19fb18f16fe70ed8` | 轮询/发布中弘能力、模式、风速和温度实体 | 所有消费者迁移并通过观察期后再禁用 |

另外，多个已禁用的历史 tab 仍保留中弘实体引用，包括“中央空调对接（新版未完成）”、
“空调滋水”、“中央空调对接OLD/DEV”和“科力屋测试”。它们当前不构成在线控制依赖，但封存时
必须保留为明确禁用的归档或完成引用清理，防止日后误启用后重新形成旧控制链。

本地重构脚本：

- `hl-gateway-lab/tools/patch_ac_native_modes_fan_v56.js`
- `hl-gateway-lab/tools/test_ac_native_modes_fan_v56.js`
- `hl-gateway-lab/tools/patch_zhonghong_supplemental_v2.js`
- `hl-gateway-lab/tools/test_zhonghong_supplemental_v2.js`

上述脚本已经形成并部署 V56 的目标架构：“原生精确模式为权威、cmd243 温度为主源、中弘为
只读观察者和最后兜底”。V56 上线解决了控制权威和精确模式/风速语义，但 cmd243 当前没有数据，
因此不能用“V56 已部署”推导出中弘读取依赖已经解除。

## 8. 中弘明确退出门槛

以下条件必须全部满足，才可把中弘从“只读补充”改为“可封存”。

### A. 大金原生数据等价性

1. 10 个原生 climate 连续提供新鲜、可验证的 power、精确 mode、目标温度和 fan 状态。
2. 10 个精确模式 select 均可用，并在制冷、清爽、睡眠、送风、关机等实机转换后与网关状态一致。
3. 厨房和大卫生间持续保持两档语义；其余 8 台保持 1–5 档语义，不发生映射回退。
4. 大金原生协议必须实际返回 10 房回风温度。cmd243 仅收到 ACK 不算满足；需要带房间 TLV 的
   数据响应、合理数值、时间戳和有效期。若改用另一条大金官方协议，也必须达到相同证据质量。
5. 若现有控制逻辑实际需要回风湿度，则 10 房湿度也必须达到同一标准；不能用目标湿度替代。
6. 若任何消费者需要压缩机运行、频率、盘管/翅片或冷媒数据，必须找到原厂协议的真实字段并实测；
   `hvac_action` 不得作为替代证据。

### B. 消费者迁移

1. AC Master 的所有命令目标继续只允许原生 `ds_air`，且生产 flow 中不存在对中弘 climate 的
   service call。
2. AC Master V56 已完成回归、备份、部署和线上冷启动验证；后续修改仍须重复这一验证。
3. 第 7 节列出的全部启用 Node-RED 读取/监听依赖迁移完成。
4. 审计 HA automations、scripts、templates、dashboards、MQTT discovery 和 entity registry，确认
   没有未登记的中弘消费者。
5. 所有禁用历史 tab 保持明确归档，不能因中弘实体消失而在未来误启用时产生静默错误。

### C. 并行观察期

1. 大金与中弘并行只读至少 24–72 小时，覆盖关机、制冷、清爽、睡眠及风速变化。
2. 记录每房温度差、模式差、风速差和数据新鲜度；阈值必须基于实际曲线确定，不能预先编造。
3. 观察期内原生主源不应触发中弘 fallback；任何 fallback 都必须查明原因并重新计时。
4. power/mode/fan 的确认必须来自网关状态坐标；通用 ACK 不计作内机执行成功。
5. 清爽温度补偿和“达标后交还自动风速”的生产行为不再出现频繁跳档。

### D. 封存操作

1. 先备份 Node-RED flow、中弘相关 HA entity registry 和集成配置。
2. 先禁用中弘轮询/发布与集成，保留归档，不立即删除历史实体和证据。
3. 再观察至少一个完整运行周期，确认 AC Master、温度补偿、空调水系统及面板无缺失输入。
4. 最后才考虑断开中弘网关；若任何依赖复现，从备份恢复只读补充链，而不是恢复中弘控制权。

## 9. 当前决策

| 问题 | 当前答案 |
| --- | --- |
| 大金能否作为 10 房唯一命令权威？ | **可以，已具备并已实测原生状态闭环。** |
| 大金能否正确区分清爽、睡眠等独立模式？ | **可以，1.3.18 精确 select 与属性已上线。** |
| 大金能否正确表达五档机与两档机风速？ | **可以，10 房实体能力已上线。** |
| AC Master V56 是否已上线？ | **已上线；冷启动未水合误写已根因修复，最终 SHA 如第 7 节。** |
| 大金当前能否提供本系统所需的 10 房回风温湿度？ | **不能证明；cmd243 只有 SYS_ACK，无数据帧。** |
| 当前能否封存中弘？ | **不能。仍有回风温度和现有 Node-RED 读取依赖。** |
| 何时可以封存？ | **第 8 节全部门槛通过后。** |

最终原则很简单：如果大金原生协议将所有实际消费者所需数值都以可验证、可持续的新鲜数据提供，
并且经过依赖迁移和并行观察，中弘就可以封存；在此之前，中弘只能保留为只读补充，不能成为控制权威。
