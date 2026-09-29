# Lab 3 Part 2 — Coffee Order

半自动语音点单原型：麦克风 → faster-whisper → PiTFT 显示回答 → 操作者 A 接受 / B 重试 → Piper 回复。每次只点一杯，不包含价格、不加单、不执行支付或发送订单。

## 文件

| 文件 | 用途 |
| --- | --- |
| `coffee_order.py` | 主程序：对话、屏幕、按钮、录音、识别、Piper 和日志 |
| `setup_coffee.sh` | 首次安装依赖，复用 Part 1 模型，缺失时才下载 |
| `run_coffee.sh` | 启动环境、检查旧屏幕服务和重复运行 |
| `requirements.txt` | Python 依赖 |
| `config.example.json` | 默认配置；复制为 `config.json` 后可设置音频设备 |
| `tests/test_coffee_order.py` | 无需硬件的逻辑测试 |

## 硬件与模型

- Raspberry Pi 5，沿用 Lab 2 的 Adafruit Mini PiTFT 1.14 英寸 ST7789，横屏 240 × 135。
- SPI：CS GPIO5，DC GPIO25；背光 GPIO22；A GPIO23、B GPIO24，按下时为低电平（输入上拉、active LOW）。使用与 `Lab 2/plant_clock.py` 相同的显示偏移和旋转。
- 一个独立麦克风、一个扬声器。只在 Listening 时采集声音，播放、识别和人工确认时关闭输入流。
- TTS：Part 1 的 **Piper en_US-lessac-medium**，复用 `Lab 3/voices/en_US-lessac-medium.onnx` 和 `.onnx.json`。
- ASR：Part 1 的 **faster-whisper tiny.en / CPU int8**。
- 语音结束检测：Part 1 的 **Silero VAD / sherpa-onnx**，模型位于 `Lab 3/models/silero_vad.onnx`。

## 在树莓派上安装与启动

先把这个 `coffee-order` 目录放到现有仓库的 `Lab 3` 目录下。模型不用上传 GitHub。

如果仓库没有本地修改冲突，可以同步：

```bash
cd ~/Interactive-Lab-Hub
git switch Fall2026
git pull --ff-only origin Fall2026
cd "Lab 3/coffee-order"
bash setup_coffee.sh
bash run_coffee.sh --check
bash run_coffee.sh
```

如果 `git pull` 提示本地文件冲突，先停下来保留文件，不要使用 reset/clean 强行覆盖。也可以下载提供的 ZIP，将其中 `coffee-order` 文件夹单独放进 `Lab 3`；原来的 `speech-scripts`、Lab 2 程序和模型不需要改动。

安装脚本使用现有 `Lab 3/.venv`，不升级已满足版本约束的依赖；没有环境时才新建。安装需要网络，首次下载 tiny.en 也需要网络。安装完成且模型已缓存后，点单不依赖云端语音服务或 API key。

如要使用独立环境，两次都指定同一路径：

```bash
COFFEE_VENV="$HOME/coffee-venv" bash setup_coffee.sh
COFFEE_VENV="$HOME/coffee-venv" bash run_coffee.sh
```

如果旧的 `piscreen.service` 正在占用 GPIO，启动脚本会给出提示。先临时停止它再启动：

```bash
sudo systemctl stop piscreen.service
bash run_coffee.sh
```

程序不会自动禁用旧服务。以后需要恢复 Lab 2 开机屏幕时：

```bash
sudo systemctl start piscreen.service
```

## 选择正确的麦克风和播放器

默认沿用系统默认输入与输出。若选错设备，先运行：

```bash
bash run_coffee.sh --list-devices
```

从输出中分别选取带输入通道的麦克风、带输出通道的播放器。可以使用列表中的编号，或能唯一匹配的名称片段。例如将下面占位文字替换为实际设备名称：

```bash
bash run_coffee.sh --input-device 'YOUR MICROPHONE NAME' --output-device 'YOUR SPEAKER NAME'
```

**这里是 PortAudio 的编号，不是 `arecord -l` 的 ALSA card 编号。Part 1 的 `plughw:4,0` 不代表这里也填 4。**

也可以修改本目录的 `config.json`，设置 `input_device` 和 `output_device`，以后启动无需重复填写。相对路径配置都相对于 `coffee_order.py` 所在目录。

## 实际操作

1. 启动时等待模型加载。设备播报：`Welcome! We have Latte, Cappuccino, and Mocha. Which would you like?`
2. 屏幕显示 Listening 和三种饮品，顾客说出选择。
3. 约 0.8 秒连续静音后进行识别，显示原话和程序提取的选项。
4. **操作者按 A 接受；按 B 则不更新订单，提示重说并重新收音。**
5. 依次询问 Hot / Iced、Small / Medium / Large，每个回答都需要 A/B 检查。
6. 直接核对完整订单，不询问是否加单，不出现价格或总价。
7. 顾客说 Yes，操作者按 A，才完成确认；顾客说 No，操作者按 A，进入修改。
8. 修改时先选择 Drink / Temperature / Size，再说出新值；每次都经过 A/B 检查，完成后再次核对。
9. 播报柜台付款提示，屏幕停留在最终订单。按终端 Ctrl+C 结束，重新启动可测试下一位顾客。结束程序会释放 GPIO 并关闭背光。

按钮只在 Check answer 时有效；先释放两个按钮，再短按其中一个。按住、抖动或同时按两个按钮不会自动跳过步骤。长回答每 2.5 秒自动翻页，底部始终保留 A/B 提示。

## 特殊情况与边界

- 0.8 秒是检测到说话之后的静音阈值。5 秒是等待首次开口的时间，开始说话后不会在第 5 秒强行截断。
- 没开口：询问 `Would you like more time?`，然后重新收音。
- ASR 没有结果、录音溢出或超过 20 秒：丢弃当前回答并提示重说，不更新订单。
- B 只丢弃本次结果，保留之前已确认的饮品、冷热和杯型。
- `Medium... actually, large` 支持显式改口；没有明确改口信号的多个选项会要求澄清。
- 菜单外饮品、不符合当前问题的答案，即使按 A 确认听写正确，也会重问当前问题。
- 顾客主动问价格时，说明此原型不包含价格，再返回当前问题。
- 简单规则提取选项，并非通用自然语言助手。复杂表达、噪声或口音可能识别失败；使用 B 重试或更清晰地表达。A 前同时检查原话和黄色 Choice 提示。
- 麦克风只在输入流实际打开后才显示 Listening。Piper 合成时显示 Processing，开始播放时显示 Speaking。
- 默认不强制将背景噪声识别成菜单选项；不使用订单词表提示把无关语音诱导为有效选项。操作者仍需检查 ASR 是否听对。

## 测试与实验记录

无需树莓派即可检查对话逻辑：

```bash
python coffee_order.py --simulate
python -m unittest discover -s tests -v
```

模拟模式先输入顾客的识别文本，再输入 A 或 B。可输入 `:silence`、`:fail`、`:long` 测试异常；模拟模式不验证真实麦克风、Piper、VAD 或 GPIO。

每次运行在 `runs/日期-编号/events.jsonl` 保存状态、识别文本、候选解释、按钮、订单变化和耗时，终端同步显示，方便录制控制端。默认不保存音频；需要收集实验语音时：

```bash
bash run_coffee.sh --save-audio
```

录音 WAV、日志、实际设备配置均保留在树莓派，已加入 `.gitignore`，不会随正常 Git 提交上传。

树莓派现场检查清单：

- 确认欢迎语是之前的 Piper 声音，麦克风和播放器选对。
- 检查菜单同时显示三种饮品，屏幕方向和 A/B 对应正确。
- 先试 Latte → Iced → Large → Yes，每个回答按 A。
- 故意在一个识别结果上按 B，确认订单没有被更新。
- 试 `Medium... actually, large`，中间约停顿半秒。
- 保持安静超过 5 秒，确认提示更多时间，而不是自动接受。
- 核对时说 No 并按 A，修改杯型，再核对。
- 按住 A 或 B，确认不会连续跳步；两键同时按下应被忽略。
- 至少找两人测试并录制设备与操作者按钮操作。程序日志不能代替课程要求的视频。

## 常见问题

- `GPIO busy`：旧的屏幕/植物时钟程序仍在运行。退出旧程序，或按上述方法临时停止 `piscreen.service`。不要同时运行两个使用屏幕的程序。
- `No module named ...`：使用 `bash run_coffee.sh` 启动，它会选用 Lab 3/.venv；运行安装脚本补齐依赖。
- 看不到 SPI 设备：在 `sudo raspi-config` 中开启 SPI，按提示重启；这与 Lab 2 相同。
- 没声音或无法录音：先检查 `--list-devices`，再选择实际设备；确认输入支持 16 kHz 单声道。
- `--check` 只验证依赖、模型文件、音频格式；不实际占用 GPIO，不意味着实体屏幕和按钮已经通过测试。

## 参考

语音基础沿用本仓库 `../speech-scripts/echo_bot.py` 和 `listen.py`，显示配置沿用 `../../Lab 2/plant_clock.py`。

- [Piper Python API](https://github.com/OHF-Voice/piper1-gpl/blob/main/docs/API_PYTHON.md)
- [sherpa-onnx 麦克风 VAD 示例](https://github.com/k2-fsa/sherpa-onnx/blob/master/python-api-examples/vad-microphone.py)
