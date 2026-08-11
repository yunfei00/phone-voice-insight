# Phase 5 PoC v2 样本预览

- Sample version: `phase5-poc-v2`
- Seed: `20260808`
- Count: `20`
- AI status: `NOT_RUN`

## Sample 01

- Review ID: `473`
- Record Type: `REPLY`
- Content Purpose: `PRODUCT_EXPERIENCE`

### 当前正文

> 133版本的

### 必要上下文

> 父帖标题：续航有问题
> 父帖正文：不是，这续航咋回事啊，待机啥也没干，后台也没有开什么应用，怎么待机24小时，电量直接掉了9%啊，被云控了吗？
> 明明查那个bug报告，充电只充了10次，容量还是10080的啊？充10次后，电池健康度衰减这么厉害的吗？
> 耗电排行里面的耗电量和电池下降的百分比计算出的耗电量不匹配啊？啥情况啊？而且，在凌晨的时候，明明显示的耗电排行没有耗电的，怎么电量还是下降了啊？

### 产品体验 Signal

- 判定依据：CONTEXT:BATTERY:续航；CONTEXT:BATTERY:耗电；CONTEXT:BATTERY:电量；CONTEXT:BATTERY:电池；CONTEXT:BATTERY:待机；CONTEXT:CHARGING:充电；CONTEXT:SYSTEM_BUG:bug；CONTEXT:DISPLAY:显示
- 候选 Aspect：BATTERY, CHARGING, SYSTEM_BUG, DISPLAY
- Context Required：YES

---

## Sample 02

- Review ID: `472`
- Record Type: `REPLY`
- Content Purpose: `PRODUCT_EXPERIENCE`

### 当前正文

> 而且我的系统没有升级过，买的时候就是这个系统版本的

### 必要上下文

> 父帖标题：续航有问题
> 父帖正文：不是，这续航咋回事啊，待机啥也没干，后台也没有开什么应用，怎么待机24小时，电量直接掉了9%啊，被云控了吗？
> 明明查那个bug报告，充电只充了10次，容量还是10080的啊？充10次后，电池健康度衰减这么厉害的吗？
> 耗电排行里面的耗电量和电池下降的百分比计算出的耗电量不匹配啊？啥情况啊？而且，在凌晨的时候，明明显示的耗电排行没有耗电的，怎么电量还是下降了啊？

### 产品体验 Signal

- 判定依据：CONTEXT:BATTERY:续航；CONTEXT:BATTERY:耗电；CONTEXT:BATTERY:电量；CONTEXT:BATTERY:电池；CONTEXT:BATTERY:待机；CONTEXT:CHARGING:充电；CONTEXT:SYSTEM_BUG:bug；CONTEXT:DISPLAY:显示
- 候选 Aspect：BATTERY, CHARGING, SYSTEM_BUG, DISPLAY
- Context Required：YES

---

## Sample 03

- Review ID: `463`
- Record Type: `REPLY`
- Content Purpose: `PRODUCT_EXPERIENCE`

### 当前正文

> 不行啊！就播放几秒钟又停了

### 必要上下文

> 父帖标题：求解求解
> 父帖正文：看快手或者抖音时，返回到后台播放就几秒钟，然后就停了，没有声音了，只能在从新打开！这是怎么回事儿呀
> 作者声明：作品含AI生成内容

### 产品体验 Signal

- 判定依据：CONTEXT:AUDIO_AND_CALL:声音表现
- 候选 Aspect：AUDIO_AND_CALL
- Context Required：YES

---

## Sample 04

- Review ID: `471`
- Record Type: `THREAD`
- Content Purpose: `QUESTION`

### 当前正文

> 不是，这续航咋回事啊，待机啥也没干，后台也没有开什么应用，怎么待机24小时，电量直接掉了9%啊，被云控了吗？
> 明明查那个bug报告，充电只充了10次，容量还是10080的啊？充10次后，电池健康度衰减这么厉害的吗？
> 耗电排行里面的耗电量和电池下降的百分比计算出的耗电量不匹配啊？啥情况啊？而且，在凌晨的时候，明明显示的耗电排行没有耗电的，怎么电量还是下降了啊？

### 必要上下文

> N/A

### 产品体验 Signal

- 判定依据：BATTERY:续航；BATTERY:耗电；BATTERY:电量；BATTERY:电池；BATTERY:待机；CHARGING:充电；SYSTEM_BUG:bug；DISPLAY:显示
- 候选 Aspect：BATTERY, CHARGING, SYSTEM_BUG, DISPLAY
- Context Required：NO

---

## Sample 05

- Review ID: `414`
- Record Type: `REPLY`
- Content Purpose: `PRODUCT_EXPERIENCE`

### 当前正文

> 待机时间和信号确实强悍

### 必要上下文

> N/A

### 产品体验 Signal

- 判定依据：BATTERY:待机；SIGNAL:信号
- 候选 Aspect：BATTERY, SIGNAL
- Context Required：NO

---

## Sample 06

- Review ID: `163`
- Record Type: `THREAD`
- Content Purpose: `PRODUCT_EXPERIENCE`

### 当前正文

> 后盖照相机位置连续更换开裂
> 作者声明：作品含AI生成内容

### 必要上下文

> N/A

### 产品体验 Signal

- 判定依据：BUILD_QUALITY:后盖
- 候选 Aspect：BUILD_QUALITY
- Context Required：NO

---

## Sample 07

- Review ID: `154`
- Record Type: `THREAD`
- Content Purpose: `QUESTION`

### 当前正文

> 充电慢不说，要1个多小时才充满，拍照比以前的老人机还模糊是怎么回事，拍照不防抖轻微抖动下拍出来的照片模糊的一塌糊涂，3个摄像头只有1个能用其他2个是摆设吗，信号也没有说的这么好，该转圈圈还是转！，工作拍的照片客户根本看不清，工程师也没能解决我的问题，最后一张图是4年前的手机拍出来，虽然不是很清晰但也不模糊！

### 必要上下文

> N/A

### 产品体验 Signal

- 判定依据：CHARGING:充电；SIGNAL:信号；CAMERA:拍照；CAMERA:摄像；CAMERA:拍出来
- 候选 Aspect：CHARGING, SIGNAL, CAMERA
- Context Required：NO

---

## Sample 08

- Review ID: `78`
- Record Type: `THREAD`
- Content Purpose: `PRODUCT_EXPERIENCE`

### 当前正文

> 荣耀
> power2目前为止是续航最强的存在了，应该没有谁能超越了吧！

### 必要上下文

> N/A

### 产品体验 Signal

- 判定依据：BATTERY:续航
- 候选 Aspect：BATTERY
- Context Required：NO

---

## Sample 09

- Review ID: `74`
- Record Type: `THREAD`
- Content Purpose: `PRODUCT_EXPERIENCE`

### 当前正文

> 遇到堵车移动和广电网络不稳定，卡的听小说都会卡顿

### 必要上下文

> N/A

### 产品体验 Signal

- 判定依据：SIGNAL:网络；SYSTEM_FLUENCY:卡顿
- 候选 Aspect：SIGNAL, SYSTEM_FLUENCY
- Context Required：NO

---

## Sample 10

- Review ID: `137`
- Record Type: `REPLY`
- Content Purpose: `QUESTION`

### 当前正文

> 半仙power2的来电还是自动免提吗？另外WinRT信号和它相比那个能好些？

### 必要上下文

> N/A

### 产品体验 Signal

- 判定依据：SIGNAL:信号；AUDIO_AND_CALL:免提
- 候选 Aspect：SIGNAL, AUDIO_AND_CALL
- Context Required：NO

---

## Sample 11

- Review ID: `70`
- Record Type: `REPLY`
- Content Purpose: `PRODUCT_EXPERIENCE`

### 当前正文

> 不是错觉
> 一天一充了

### 必要上下文

> N/A

### 产品体验 Signal

- 判定依据：BATTERY:一天一充
- 候选 Aspect：BATTERY
- Context Required：NO

---

## Sample 12

- Review ID: `187`
- Record Type: `REPLY`
- Content Purpose: `QUESTION`

### 当前正文

> 为啥是4g网络？地方网络不行吗

### 必要上下文

> N/A

### 产品体验 Signal

- 判定依据：SIGNAL:4g；SIGNAL:网络
- 候选 Aspect：SIGNAL
- Context Required：NO

---

## Sample 13

- Review ID: `432`
- Record Type: `REPLY`
- Content Purpose: `PRODUCT_EXPERIENCE`

### 当前正文

> 掉电快

### 必要上下文

> N/A

### 产品体验 Signal

- 判定依据：BATTERY:掉电
- 候选 Aspect：BATTERY
- Context Required：NO

---

## Sample 14

- Review ID: `48`
- Record Type: `REPLY`
- Content Purpose: `PRODUCT_EXPERIENCE`

### 当前正文

> 我也感觉续航掉了。购买了不到一月，最近使用起来，感觉没有宣传说的那么省点

### 必要上下文

> N/A

### 产品体验 Signal

- 判定依据：BATTERY:续航
- 候选 Aspect：BATTERY
- Context Required：NO

---

## Sample 15

- Review ID: `457`
- Record Type: `REPLY`
- Content Purpose: `QUESTION`

### 当前正文

> 我就想问怎么回归原生态？再也不系统升级了，发烫的要死。

### 必要上下文

> N/A

### 产品体验 Signal

- 判定依据：HEATING:烫
- 候选 Aspect：HEATING
- Context Required：NO

---

## Sample 16

- Review ID: `350`
- Record Type: `REPLY`
- Content Purpose: `PRODUCT_EXPERIENCE`

### 当前正文

> 电池容量够大

### 必要上下文

> N/A

### 产品体验 Signal

- 判定依据：BATTERY:电池
- 候选 Aspect：BATTERY
- Context Required：NO

---

## Sample 17

- Review ID: `125`
- Record Type: `REPLY`
- Content Purpose: `PRODUCT_EXPERIENCE`

### 当前正文

> 我的手机耗电很快，信号不好

### 必要上下文

> N/A

### 产品体验 Signal

- 判定依据：BATTERY:耗电；SIGNAL:信号
- 候选 Aspect：BATTERY, SIGNAL
- Context Required：NO

---

## Sample 18

- Review ID: `128`
- Record Type: `REPLY`
- Content Purpose: `PRODUCT_EXPERIENCE`

### 当前正文

> 震我V13信号不好的地方，用这个机子信号一样不行

### 必要上下文

> N/A

### 产品体验 Signal

- 判定依据：SIGNAL:信号
- 候选 Aspect：SIGNAL
- Context Required：NO

---

## Sample 19

- Review ID: `358`
- Record Type: `REPLY`
- Content Purpose: `PRODUCT_EXPERIENCE`

### 当前正文

> 本身就是个续航小金刚，还兼顾到给别的设备充电。击碎了我的续航焦虑。

### 必要上下文

> N/A

### 产品体验 Signal

- 判定依据：BATTERY:续航；CHARGING:充电
- 候选 Aspect：BATTERY, CHARGING
- Context Required：NO

---

## Sample 20

- Review ID: `268`
- Record Type: `REPLY`
- Content Purpose: `QUESTION`

### 当前正文

> 我的荣耀趴窝二，现在已经锁死到160版本了。
> 你现在这个版本，会不会影响手机续航？
> 用几天，再给大家回复一下

### 必要上下文

> N/A

### 产品体验 Signal

- 判定依据：BATTERY:续航
- 候选 Aspect：BATTERY
- Context Required：NO

---
