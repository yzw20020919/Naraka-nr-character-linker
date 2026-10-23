# Naraka NR Character Linker

[English documentation](README_EN.md)

用于 Blender 的 Ninja Ripper `.nr` 模型整理插件，适合处理《永劫无间》（Naraka: Bladepoint）导出的 `frame_*` 捕获文件夹。

插件会自动识别可能的角色网格组，连接 UV、颜色贴图和法线贴图，并将静态角色整理到 Blender 坐标中。

## 功能

- 读取 `frame_*` 文件夹中的 Pre-VS 三角网格。
- 自动过滤重复绘制通道，并选择较完整的角色网格组。
- 创建 UV Map 和 Principled BSDF 材质。
- 连接颜色贴图和法线贴图。
- 使用 FFmpeg 转换 DDS 等 Blender 不便直接处理的贴图格式。
- 自动将角色摆正，脚底放到 `Z = 0`。
- 默认让角色面部朝向 Blender 的 `-Y` 方向。
- 创建前视、后视相机和基础灯光，方便检查模型。
- 自动修复部分捕获中脱离身体的脸部、眼睛、发帽和发丝绘制部件。
- 清理无效三角面并重算法线；实体服装和身体可使用 0–2 级细分曲面提高显示精度。

## 安装

1. 在 GitHub 的 **Releases** 页面下载 `naraka_nr_character_linker_addon.zip`。
2. Blender 4.2 或更高版本：打开 **Edit > Preferences > Get Extensions**，点击右上角菜单，选择 **Install from Disk**。
3. Blender 3.6–4.1：打开 **Edit > Preferences > Add-ons > Install**。
4. 选择下载的 ZIP，并启用 **Naraka NR Character Linker**。
5. 回到 3D View，按 `N` 打开侧栏，进入 **Naraka NR** 标签。

插件 ZIP 的顶层必须包含 `r_character_linker` 文件夹，并且其中有 `__init__.py` 文件。Release 中提供的安装包已经符合这个目录结构。

## 使用方法

1. 将 **Capture folder** 设置为包含 `.nr` 文件的 `frame_0` 或 `frame_1` 文件夹。
2. **Group ID** 留空时，插件会自动识别角色组。如果识别结果不正确，可以填写文件名中的组编号，例如 `37` 或 `1007`。
3. 如果 DDS 等贴图需要转换，在 **FFmpeg path** 中填写 FFmpeg 可执行文件路径，例如：

   ```text
   C:\Tools\ffmpeg\bin\ffmpeg.exe
   ```

   如果 `ffmpeg` 已经加入系统 PATH，也可以留空。

4. **Output folder** 可以留空。留空时，已保存的 `.blend` 会将转换后的贴图写入工程旁边的 `nr_blender_output` 文件夹；未保存的工程会写入用户目录下的 `Naraka_NR_Output` 文件夹。
5. 点击 **Import and link character**。

导入前可在面板中调整 **Repair detached face and hair** 和 **Geometry refinement**。前者默认开启，会把头部相关绘制通道按脸部位置校正；后者默认是 0，以减少高面数网格的视口负担，需要时可手动提高。插件会结合 Alpha 分布和颜色特征识别发丝贴图并进行清晰裁切；蕾丝、薄纱等同时包含透明、实心和柔和过渡区域的颜色贴图会保留连续 Alpha，尽量避免镂空显示成黑色。明显属于打包数据的 Alpha 不会连接到透明度。

导入的模型会放在 `NR_Character` 集合中，转换后的贴图位于输出目录的 `textures` 子目录。

## 识别组失败时

自动识别适用于常见的 Naraka 捕获结构，但不同场景可能存在多个相似网格组。如果导入的不是目标角色：

1. 查看捕获文件名，例如 `mesh_37_....nr`。
2. 将 `Group ID` 填写为 `37`。
3. 再次点击 **Import and link character**。

## 限制

Ninja Ripper 捕获通常不包含游戏原始骨骼、蒙皮权重、动画控制器或专用 Shader。因此本插件恢复的是静态网格、UV、主要颜色贴图和法线贴图，不能完整恢复游戏内的动画系统和最终渲染效果。

贴图转换只改变文件格式，不会增加捕获文件中原本不存在的细节。如果原始捕获贴图分辨率较低，Blender 中的贴图也会保持相同分辨率。

插件不会修改原始捕获文件夹中的 `.nr` 文件和贴图。

## 项目结构

```text
r_character_linker/
  __init__.py          # Blender 面板、导入器、材质和坐标整理
  nrfile.py            # Ninja Ripper .nr 文件解析器
  README_中文.md        # 中文补充说明
LICENSE                # MIT 许可证
README.md              # 项目说明
CONTRIBUTING.md        # 贡献指南
```

## 许可证

本项目使用 [MIT License](LICENSE)。你可以自由使用、修改和再发布代码，但需要保留原许可证和版权声明。

请注意：本插件代码与用户自己的模型、贴图、游戏捕获文件是不同的内容。不要将游戏资源、角色贴图或 `.nr` 捕获文件上传到公开仓库，除非你拥有相应的发布权利。

## 贡献

欢迎提交 Issue 和 Pull Request。提交问题时，请尽量提供 Blender 版本、操作系统、捕获格式、组编号以及错误信息。详细规则见 [CONTRIBUTING.md](CONTRIBUTING.md)。
