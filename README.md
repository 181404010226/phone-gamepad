# Phone Gamepad · WiFi 四人手柄

把 Android 手机变成 Windows 游戏的 Xbox 360 手柄。手机与电脑连接同一 Wi-Fi，自动发现电脑并分配玩家 1～4，无需配对码。

支持横屏双摇杆、方向键、ABXY、肩键、扳机、多点触控和自定义按钮映射。第五台手机等待空位，断线后自动松开输入。仓库还保留了一块键盘模拟两个手柄的原版工具。

## 下载和使用

在 [Releases](https://github.com/181404010226/phone-gamepad/releases) 下载：

- `phone-gamepad-4players.apk`：Android 手机端，Android 8.0 及以上。
- `PhoneGamepadReceiver.exe`：Windows x64 独立电脑接收端，无需安装 Python。
- `PhoneGamepad-Windows-x64.zip`：EXE、许可证与说明的完整包。
- `SHA256SUMS.txt`：安装包校验值。

1. 在 Windows 10/11 x64 运行接收端。首次使用点击“安装手柄驱动”，安装官方 ViGEmBus 1.22.0，按系统提示重启。
2. Windows 防火墙询问时允许专用网络。使用 UDP 26761，手机和电脑必须处于可互通的局域网。
3. 在最多四台手机安装 APK 并打开。玩家编号按加入顺序分配；在游戏中按 START / 加入。
4. 手机进入后台、断线或电脑端退出时，输入会自动归零。先关闭其他虚拟手柄程序，避免占满 Windows 的四个 XInput 位置。

如果自动发现失败，检查 Wi-Fi 的 AP/访客隔离、VPN 和 Windows 防火墙；也可在手机设置里手动填写电脑 IP。Windows EXE 未进行商业代码签名，系统可能显示信誉提示。

**网络边界：** 当前协议按需求省去了配对与身份认证，输入通过局域网 UDP 传输。请只在可信任的家庭/朋友网络中使用；不要映射端口到互联网或在公共 Wi-Fi 开启接收端。

## 源码结构

| 目录 | 内容 |
| --- | --- |
| `android/` | 原生 Java 手机界面、自动发现与 APK 构建脚本 |
| `pc/` | Python/tkinter 接收端、四人会话协议、测试及第三方运行库 |
| `keyboard/` | 原版双人键盘映射工具、改键界面和测试 |
| `scripts/` | Windows 独立 EXE 构建脚本 |

## 从源码运行与构建

### Windows 接收端

需要 Python 3.10+ x64（含 tkinter），第三方 vgamepad 运行库已附带，无需执行其旧版驱动安装流程。

```powershell
python pc/receiver.py
python -m unittest discover -s pc/tests -v
python -m pip install -r requirements-build.txt
python scripts/build_windows.py
```

输出位于 `dist/PhoneGamepadReceiver.exe`。`--preview` 参数可在不连接虚拟手柄的情况下测试网络。日志保存在 `%LOCALAPPDATA%/PhoneGamepad/receiver.log`。

### Android APK

需要 JDK 17、Android SDK Platform 35、Build Tools 35.0.0，构建脚本面向 Windows，无需 Gradle。

```powershell
python android/build.py --sdk D:/Android/Sdk --jdk D:/Java/MicrosoftJDK17 --work work/android --output dist/phone-gamepad.apk
```

首次构建会在 `--work` 指定的目录生成私有签名密钥和 `signing.json`。请妥善备份并保密，后续覆盖安装必须使用同一密钥。仓库与源码包不包含发布签名密钥。

### 双人键盘版

```powershell
python keyboard/app.py
python -m unittest discover -s keyboard/tests -v
```

F11 启动/暂停，F12 紧急暂停。键盘版会占用两个 XInput 位置，建议与四人手机版分别运行。

## 许可与依赖

项目原创代码采用 [MIT License](LICENSE)。第三方代码和二进制文件遵守各自许可证，参见 [THIRD_PARTY.md](THIRD_PARTY.md)。ViGEmBus 已停止上游维护，本项目使用已发布的官方 1.22.0 驱动，不代表所有游戏、反作弊环境或未来 Windows 版本都兼容。

发布前会执行协议/键盘自动化测试、APK 签名校验及 Windows EXE 检查。既有开发记录中四路虚拟手柄曾通过 XInput 实测；具体游戏兼容性仍由对应游戏决定。
