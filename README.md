# Daikin DS-AIR Custom Component For Home Assistant

此项目是Home Assistant平台[DS-AIR](https://www.daikin-china.com.cn/newha/products/4/19/DS-AIR/)以及[金制空气](https://www.daikin-china.com.cn/newha/products/4/19/jzkq/)自定义组件的实现

支持的网关设备型号为 DTA117B611/DTA117C611/DTA117D611，其他网关的支持情况未知。DTA117D611 使用已实机验证的固定协议布局，不会被后续通用 ACK 改变解析方式。

## HongyeVilla 1.3.23 扩展

- 大金原生 `climate` 是唯一控制入口；中弘不参与模式、设定温度、风速、风向或开关控制。
- 可选的“中弘只读诊断与回风温度”读取 `0x50` 状态帧中的在线状态、故障码、运行字段和回风温度；只有回风温度会在 DS-AIR 原生值缺失时补入 climate，数据超过 120 秒即失效。
- 每台内机新增“机组诊断”和本地 `cmd9`“滤网清洗提醒”；“复位滤网清洗提醒”按钮使用原厂本地 `cmd21`，不会经过中弘或云端。
- 本地 `cmd10` 仅为 VAM/新风提供滤网已用百分比，并在 HA 显示为剩余百分比。普通内机的累计时长来自金制空气云端接口，本集成不会把它伪装成本地数值。
- 五档内机在原生面板显示 `1`–`5` 和自动风速，厨房/卫浴两档机继续显示低/高。
- 清爽、自动除湿、睡眠等原厂扩展工作模式通过原生 climate 的预设模式入口呈现，同时保留精确工作模式实体供诊断和自动化使用。
- 对网关能力位未声明、但已由现场系统确认可用的制热能力，只能通过显式配置覆盖启用，并在实体属性中保留原始能力位与覆盖来源。

部署和验证证据见 [1.3.23 上线记录](reports/ds-air-1.3.23-local-diagnostics-and-filter-reset-20260721.md)。

# 支持设备

* 空调
* 空气传感器

# 不支持设备

* 睡眠传感器
* 晴天轮
* 转角卫士
* 金制家中用防护组件
* 显示屏(黑奢系列)

# 接入方法

1. 将项目ha-air目录部署到自定义组件目录，一般路径为```~/.homeassistant/custom_components/```  
   或使用hacs载入自定义存储库，设置URL```https://github.com/mypal/ha-dsair``` ，类别 ```集成```
2. 本集成已支持ha可视化配置，在配置-集成-添加集成中选择```DS-AIR``` ，依次填入网关IP、端口号、设备型号提交即可

# 开发过程

本组件开发过程可在[blog](https://www.mypal.wang/blog/lun-yi-ci-jia-yong-kong-diao-jie-ru-hazhe-teng-jing-li/)查看
