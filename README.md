# HammerVlogCut

面向日常、旅行与活动 Vlog 的本地素材审阅台。可以检查代表帧、回看原片、校正逐句对白、补充拍摄背景，再按故事时间线跨素材连续播放。调整镜头入出点或移出镜头后，应用修改即可保存一个新的编排版本。

## 启动

在 macOS 上准备 Python 3、FFmpeg 和 ffprobe，从仓库根目录运行以下命令。将素材路径换为自己的原片目录。

```sh
python3 scripts/prepare.py "/path/to/originals" "../Project/my-vlog"
python3 scripts/review.py "../Project/my-vlog"
```

用 Chrome 打开终端打印的完整本机地址。项目目录保存索引、代表帧、抽取音轨、转写和人工修订。原片只读。服务空闲后会退出，再运行第二条命令即可重新打开。

## 素材理解与故事预览

[素材语义化 Skill](SKILL.md) 描述如何结合当前对话环境的能力理解画面、声音和背景信息。初次导入会建立素材索引；转写和语义分析由实际可用的工具完成。

故事时间线按顺序记录原片文件名、入点和出点。已有编排方案可通过以下命令保存，随后从审阅台打开故事预览。

```sh
python3 scripts/story_preview.py "../Project/my-vlog" plan.json v001
```

一个最小的 `plan.json` 示例，时间单位为秒，`source` 使用项目索引中实际的相对文件名。

```json
{"title":"周末散步","version":"第一版","clips":[
  {"chapter":"出门","label":"走进公园","source":"park.mp4","in":1,"out":4}
]}
```

浏览器按时间线播放本地原片，并预载下一镜。保存写入项目的 `stories/<版本>/story.json`。

## 许可证

[MIT](LICENSE)
