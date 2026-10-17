# Naraka NR Character Linker

这是一个 Blender 插件，用来处理 Ninja Ripper 导出的 `frame_*` 文件夹：读取 `.nr` 网格、自动挑选较完整的角色组、连接捕获到的贴图，并把角色摆正到 Blender 坐标中。

## 安装

1. 下载 `naraka_nr_character_linker_addon.zip`。
2. Blender 4.2 及更新版本：打开 **Edit > Preferences > Get Extensions**，点右上角菜单并选择 **Install from Disk**。Blender 3.6–4.1 可在 **Preferences > Add-ons > Install** 中安装。
3. 选择下载的 ZIP，再到 Add-ons/已安装扩展列表中启用 **Naraka NR Character Linker**。
4. 回到 3D View，在右侧栏按 `N`，打开 **Naraka NR** 标签。

## 使用

1. 把 **Capture folder** 指向含有 `.nr` 文件的 `frame_0` 或 `frame_1` 文件夹。
2. **FFmpeg path** 可填写本机 FFmpeg 可执行文件，例如 Windows 下的 `C:\\Tools\\ffmpeg\\bin\\ffmpeg.exe`。插件使用 FFmpeg 将捕获中的 DDS 等贴图转换为 PNG；留空时会尝试从系统 PATH 查找，Blender 可直接读取的格式也可直接使用。
3. **Group ID** 留空时自动判断角色组。若自动识别结果不合适，可填捕获文件名中的编号，例如 `37`、`1007`，再运行一次。
4. 可选填写 **Output folder**。留空时，已保存的 `.blend` 会将文件写到同级 `nr_blender_output\<frame名>`；未保存的工程则写到用户目录 `Naraka_NR_Output\<frame名>`。
5. 点击 **Import and link character**。模型会放入 `NR_Character` 集合，贴图放在输出目录的 `textures` 子目录。

导入前可在面板中调整 **Repair detached face and hair** 和 **Geometry refinement**。前者默认开启，会把头部相关绘制通道按脸部位置校正；后者默认是 1，发丝卡片和被校正的头部卡片不会做细分，以免透明轮廓变形。

默认坐标整理会将角色直立、脚底对齐 `Z=0`，并让面部朝 Blender 的 `-Y` 方向，同时建立前后查看相机和简单灯光。自动识别依据网格几何、重复绘制通道、主体部件数量及贴图绑定情况；不同捕获仍可能需要手动指定组号。

## 说明

- 插件不会改写捕获目录中的原始 `.nr` 和贴图。
- 转换只改变文件格式，不主动缩小贴图；若捕获本身没有高分辨率贴图，转换无法恢复游戏资源中未捕获的细节。
- 插件恢复的是静态网格、UV 和主要颜色/法线贴图。捕获数据通常不包含角色骨骼、蒙皮权重、动画及游戏专用着色器，所以材质效果会接近捕获资源，但不能完全复现游戏内渲染。
- 重复导入时会替换 `NR_Character` 集合中的上一次插件导入结果。
