# Windows 发布说明

目标：

- 最终用户电脑不安装 Python
- 最终用户电脑不安装额外依赖
- 直接运行 `exe` 或安装包即可使用

## 最快拿成品的方式

如果你当前是 macOS，不想自己折腾 Windows 打包环境，直接用项目自带的 GitHub Actions：

1. 把项目上传到 GitHub 仓库
2. 打开仓库 `Actions`
3. 运行 `Build Windows Release`
4. 下载产物：
   - `BossLoopTimer-exe`
   - `BossLoopTimer-installer`

然后把下面任一文件发给朋友即可：

- `BossLoopTimer.exe`
- `BossLoopTimer-Setup.exe`

## 1. 在 Windows 打包机上准备

需要的仅是：

- Windows 10/11
- Python 3.10+（仅打包机需要）
- 可选：Inno Setup（如果要生成安装包）

## 2. 生成单文件 exe

双击：

```text
build-windows.bat
```

生成：

```text
dist\BossLoopTimer.exe
```

这是单文件版，已经包含 Python 运行时和项目依赖。

## 3. 生成安装包

如果打包机装了 Inno Setup，会额外生成：

```text
dist-installer\BossLoopTimer-Setup.exe
```

最终用户只需要运行这个安装包即可。

## 4. 最终用户说明

最终用户电脑：

- 不需要安装 Python
- 不需要安装数据库
- 不需要安装 Node
- 不需要额外命令行环境

数据默认保存在：

```text
%APPDATA%\BossLoopTimer\data\boss_timer.db
```
