# DS-AIR 1.3.23 本地诊断与滤网能力上线记录

日期：2026-07-21

## 结论

- 大金 DS-AIR 原生实体仍是唯一空调控制入口。
- 中弘仅建立校验和通过的 `0x50` 只读状态会话，不创建中弘控制实体，也不发送中弘控制命令。
- 每台内机新增“机组诊断”实体，合并大金本地 `cmd6` 故障证据与中弘 `0x50` 在线、故障及运行字段。
- 每台内机新增大金本地 `cmd9`“滤网清洗提醒”和本地 `cmd21`“复位滤网清洗提醒”按钮。部署及验证期间没有按下任何复位按钮。
- 大金本地 `cmd10` 只包含 VAM 房间和滤网已用百分比；创建的新风滤网剩余百分比实体不会被误用于普通内机。
- 金制空气 App 的普通内机累计时长通过云端 `app/getFilterUsedInfo` 获取，不属于已证明的本地网关字段，本版本不伪造该值。

## 协议证据边界

- 中弘 TCP-client V2.31 `0x50` 每条内机记录为 10 字节，包含外机、内机、开关、设定温度、模式、风速、回风温度、故障码、摆风和其他信息；故障码 `0x00` 为无故障，`0xFF` 为离线。
- 金制空气 App 本地 DTO 证明：
  - `SystemErrCodeDTO` / `cmd6`：设备类型、房间、故障等级、来源描述和 ASCII 故障码；
  - `SystemFilterCleanSignDTO` / `cmd9`：设备类型、房间和清洗状态；
  - `SystemFilterCleanSignResetDTO` / `cmd21`：本地复位，状态 `7` 表示复位全部滤网提醒位；
  - `SystemFilterServiceLifeDTO` / `cmd10`：VAM 房间和已用百分比，不包含普通内机累计小时。
- 不把未收到 `cmd9` 推送解释为“滤网正常”，也不把 `cmd10` 的空记录或 `0xFF` 解释为 `0%`。

## 实现与测试

- `zhonghong_temperature.py` 保留兼容名称，但观察器现解析完整只读 `0x50` 记录；温度缺失、故障或离线记录仍能进入诊断实体。
- `climate.py` 只在中弘记录在线且温度有效时补充 DS-AIR 缺失的回风温度。
- `decoder.py`、`service.py` 和 `dao.py` 增加 `cmd6`、`cmd9`、`cmd10` 的设备级证据存储；`param.py` 增加原厂字节布局的 `cmd21` 请求。
- `sensor.py` 增加内机诊断、滤网清洗提醒及 VAM 滤网剩余寿命实体；`button.py` 增加内机本地复位按钮。
- 本地回归：`python3 -m unittest discover -s tests -q`，70 项全部通过。
- 本地和 HA staging 均通过 `python3 -m compileall`；HA Core 配置检查返回 `Command completed successfully.`。

## 生产部署与备份

- 运行路径：`/usr/share/hassio/homeassistant/custom_components/ds_air`
- 线上版本：`1.3.23`
- 部署前完整目录备份：
  `/usr/share/hassio/homeassistant/backups/ds-air-before-1.3.23-20260721-023407`
- 宿主机按用户要求安装 `rsync 3.2.7`；没有启用 rsync daemon 或开放额外常驻端口。
- 部署后的 rsync dry-run 只有目录时间/属主元数据差异，源文件内容无差异。

## 线上验证

- 10 台原生大金 climate 全部存在，10/10 有有效回风温度。
- 10 个“机组诊断”实体全部为 `normal`；10/10 中弘只读记录在线，故障码均为 `0x00`。
- 10 个内机“滤网清洗提醒”实体已创建；本次启动没有收到 `cmd9`，因此全部保持 `unavailable`，未伪造正常状态。
- 10 个“复位滤网清洗提醒”按钮已创建，命令来源属性为 `daikin_official_local_cmd21`；没有执行复位。
- 1 个全屋新风“滤网剩余寿命”实体已创建。网关确认支持 `cmd10`，但本次未返回可用百分比，实体保持 `unavailable`。
- `sensor.ds_air_wang_guan_zhen_duan` 在线，网关版本为 `03.19.00`，`cmd10_supported=true`，当前没有大金本地故障码。
- 重启后的 Home Assistant 日志没有 DS-AIR 或中弘观察器错误。
- AC Master 仍为 `ok`，算法版本 `2026-07-20.ac-ectms-eco-recycle-evidence-v65`；现有 `derating_active` 和 `water_spray_active_or_requested` 是运行状态告警，本轮未改动相关逻辑。
