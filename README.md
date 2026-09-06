# TyporaPicCleaner

清理 Typora 笔记里**已经没有任何笔记引用**的图片。支持 macOS 和 Windows，命令行和图形界面都有。

零第三方依赖（只用 Python 标准库），核心是「先看清楚，再动手，动了还能撤」。

---

## 安全须知（请先读这一段）

删图是不可逆操作里最让人后悔的一类，所以这个工具的默认行为很保守：

- `scan` **只报告，不动任何文件**。想真的清理必须显式用 `clean`。
- `clean` 不调用 `rm`，而是把文件**移动**到笔记库内的 `.typora-pic-trash/<时间戳>/`，同时写一份 `manifest.json`。
- `restore` 可以按批次一键还原；还原时若原位置已有同名文件，**不会覆盖**，而是跳过并告诉你。
- 两道独立护栏：只处理图片扩展名白名单里的文件，且文件必须位于你指定的扫描目录内（`../../` 之类的路径逃不出去）。

**第一次使用，请务必先跑 `scan` 并人工过一眼清单。** 尤其注意下面这种情况：

> 如果你的图片放在统一的 `assets/` 目录里，而**有些引用它们的 .md 文件不在扫描范围内**（比如在另一个文件夹、或已被你移走），工具看不到那些引用，会把图片判为「未引用」。
>
> 报告里的 **References outside the scanned tree** 一节就是在提示这类风险。

这也是为什么 **scan / clean 接受多个笔记文件夹，并把它们当成一个整体一起比对**：几个文件夹交叉引用同一张图时，只有一起扫才不会误判。图形界面左侧的文件夹清单就是为这件事做的——一次勾好，以后每次都记得。不确定时还可以加 `--paranoid`。

---

## 安装

### 下载现成的可执行文件（推荐）

到 [Releases](https://github.com/muzi-xiaoren/TyporaPicCleaner/releases) 按需下载：

| 你的系统 | 想双击用图形界面 | 想在终端用命令 |
|---|---|---|
| macOS（Apple 芯片） | `TyporaPicCleaner-macos-arm64.zip` | `typora-pic-cleaner-cli-macos-arm64.zip` |
| macOS（Intel） | `TyporaPicCleaner-macos-x86_64.zip` | `typora-pic-cleaner-cli-macos-x86_64.zip` |

> Intel 版依赖 GitHub 的 Intel 构建机,偶尔会缺。如果 Release 里没有 x86_64 的包,直接从源码跑即可(见下),功能完全一样。
| Windows | `TyporaPicCleaner-windows.exe` | `typora-pic-cleaner-cli-windows.exe` |

macOS 的两个都是 zip，**这是故意的**：浏览器下载裸的 Unix 可执行文件会剥掉执行权限，装在 zip 里才能保住。解压后：

- 图形界面版是 `TyporaPicCleaner.app`，双击即可，**不会弹出终端窗口**
- 命令行版解压出来直接就能跑，不需要 `chmod +x`

**macOS 首次打开可能被系统拦住**（本项目未做 Apple 签名和公证）。看到「无法验证开发者」时，右键点 App → **打开**，确认一次即可；以后正常双击。或者用命令去掉隔离标记：

```bash
xattr -dr com.apple.quarantine ~/Downloads/TyporaPicCleaner.app
```

**Windows 首次打开可能出现 SmartScreen 提示**「Windows 已保护你的电脑」，点「更多信息」→「仍要运行」。

同样是未签名导致的。彻底解决需要 Apple Developer 账号和 Windows 代码签名证书，本项目暂时没有。

### 从源码运行

需要 Python 3.9+，无第三方依赖：

```bash
git clone https://github.com/muzi-xiaoren/TyporaPicCleaner.git
cd TyporaPicCleaner
python3 -m typora_pic_cleaner scan ~/Documents/Notes
python3 -m typora_pic_cleaner gui
```

> macOS 上如果报 `No module named _tkinter`，说明你的 Python 没编进 Tk（Homebrew 版常见）。用系统自带的 `/usr/bin/python3`，或 `brew install python-tk`。只有图形界面需要 Tk，命令行不需要。

### 用 pip 安装

```bash
pip install .
typora-pic-cleaner scan ~/Documents/Notes
```

---

## 界面语言

简体中文和 English。

**默认跟随系统语言**——注意这里是按系统的**首选语言顺序**判断。比如系统语言列表是 `英文 → 简体中文`，那默认就是英文界面（这是规范做法，尊重你给系统设定的优先级）。

想固定用中文，三种方式任选：

| 方式 | 做法 | 是否记住 |
|---|---|---|
| 图形界面 | 顶部菜单 **语言 / Language** → 简体中文 | **会记住**，下次启动仍是中文 |
| 命令行单次 | `typora-pic-cleaner --lang zh scan ~/Notes` | 仅本次 |
| 环境变量 | `export TPC_LANG=zh` | 由你的 shell 配置决定 |

优先级从高到低：`TPC_LANG` 环境变量 → 界面里存下的选择 → 系统语言 → 英文。

界面里选的语言存在这里（删掉即恢复跟随系统）：

- macOS / Linux：`~/.config/typora-pic-cleaner/config.json`
- Windows：`%APPDATA%\TyporaPicCleaner\config.json`

`--json` 输出里的 `layouts` 字段用的是**稳定的英文 key**，不随界面语言变化，方便脚本解析；同时另给一个已翻译的 `layouts_text` 供人看。

---

## 用法

### 先看看有哪些笔记文件夹

Typora 没有「库」的概念，笔记通常散在好几个文件夹里。先让工具找出来：

```bash
typora-pic-cleaner discover ~/Documents
```

```
/Users/me/Documents  （148 篇笔记，512 张图片）
  Notes  （120 篇笔记，480 张图片）
  Work   （26 篇笔记，31 张图片）
  Blog   （2 篇笔记，1 张图片）
```

只列出**子树里确实有你自己的笔记**的文件夹，并顺带告诉你每个里面有多少东西。

搜索会主动避开两类噪音，否则对着一整块硬盘搜会得到几百行：

| 跳过什么 | 例子 |
|---|---|
| 系统和软件目录 | `$RECYCLE.BIN`、`Program Files`、`AppData`、`Windows`、`Library`、`anaconda3`、`site-packages`、`vendor` |
| **整个文件夹的 md 全是软件自带文档** | 只有 `README.md` / `CHANGELOG.md` / `LICENSE.md` 之类的目录 |

这些 md 也**不计入上级的数量**——否则一个塞了上千个 vendored README 的目录会显示成全盘最大的笔记库。跳过了多少会在末尾告诉你。

判断刻意保守：只有当一个文件夹里的 md **全部**是那几个固定名字时才跳过，所以 `todo.md`、`index.md`、`notes.md` 这种你真会用的名字不在名单里。

**这只影响「搜索给你的建议」。** 你用 `添加…` 或直接写成命令行参数点名的目录，一律照扫不误，行上的数量也按实际全部 md 算。

### 看看有哪些图没人用

```bash
typora-pic-cleaner scan ~/Documents/Notes
typora-pic-cleaner scan ~/Documents/Notes ~/Documents/Work ~/Documents/Blog
```

**写几个文件夹就一起比对几个**，不是分别扫一遍：`Work` 里的笔记引用了 `Notes/assets/logo.png`，这张图就算「在用」。分开扫会把它判成没人用——这正是最容易误删的情况。

输出长这样（这里是英文界面；中文系统上会自动显示中文）：

```
Notes root : /Users/me/Documents/Notes
Layout     : sibling .assets folders (12 found); shared image folders (1: assets)
Scanned    : 148 note(s), 512 image(s); 468 referenced, 44 unreferenced

Unreferenced images (44, 31.2 MB reclaimable):
  8.8 MB  assets/screenshot-old.png
  4.9 MB  notes/draft.assets/image-20240102.png
  ...

Orphaned .assets folders (2, note file is gone):
  notes/deleted-post.assets

Broken references (3, the note points at a missing file):
  notes/travel.md:41  [markdown]  travel.assets/gone.png
```

四类结论各有用处：

| 分类 | 含义 |
|---|---|
| Unreferenced images | 磁盘上有、没有任何笔记引用 → `clean` 会移走这些 |
| Orphaned .assets folders | `foo.md` 已删但 `foo.assets/` 还在，且里面的图全都没人用 |
| Broken references | 笔记里写了引用但文件不存在 → 帮你反向发现笔记坏图 |
| References outside the scanned tree | 引用指向扫描范围外的真实文件 → 这部分工具不做判断 |

### 真的清理

```bash
typora-pic-cleaner clean ~/Documents/Notes          # 会打印清单并要求确认
typora-pic-cleaner clean ~/Documents/Notes -y       # 跳过确认（脚本里用）
```

### 撤销

回收站和清理历史都放在**第一个**笔记文件夹下，所以还原时把它写在前面：

```bash
typora-pic-cleaner restore ~/Documents/Notes --list        # 看清理历史
typora-pic-cleaner restore ~/Documents/Notes               # 还原最近一次
typora-pic-cleaner restore ~/Documents/Notes --id 20260903-224151
```

### 图形界面

```bash
typora-pic-cleaner gui
```

左边是文件夹清单，右边是扫描结果：

1. 点 **查找文件夹…**，选一个上层目录（比如 `~/Documents`），工具会把里面像笔记库的文件夹列出来，每行带笔记数和图片数。
2. **逐个勾选**要扫的——**搜索出来的默认一个都不勾**，没勾的不会被扫。勾上父文件夹时，它下面的子文件夹会自动标成「已含在上级」，不会被重复统计。
3. 单独的文件夹用 **添加…** 手动加；不想要的选中按 **移除**（或按 Delete 键）。
4. 图片存在笔记文件夹之外的话，在下面的「图片文件夹」里添加。
5. 点右下角**扫描**，然后在清单里取消勾选想留下的，最后**把勾选项移到回收站**。误删了点**撤销上次清理**。

**勾选结果会被记住**，下次打开原样恢复；再次「查找文件夹」时，你已经勾上的**保持勾上**，新发现的仍然不勾。文件夹如果被你删掉了，会标成「已不存在」并自动跳过。

侧栏和结果区之间、侧栏上下两块之间都可以**拖动分隔条**调宽窄，位置会被记住。外观跟随系统的浅色/深色，也可以在**设置**（菜单栏里也有）里固定，和语言一样会被记住。双击结果里的某一行可以直接在访达 / 资源管理器里定位那张图。

关于「**使用系统回收站**」这个勾选项：

| | 文件去哪 | 能不能用「撤销上次清理」 |
|---|---|---|
| **不勾（默认）** | 第一个笔记文件夹下的 `.typora-pic-trash/<时间戳>/`，附一份 `manifest.json` | ✅ 能，一键还原回原位 |
| **勾上** | 系统回收站 / 废纸篓 | ❌ 不能，只能你自己去回收站里找回 |

勾上时确认框会明确写出这一点。不确定就别勾——默认那种撤销起来省事得多。

---

## 多个文件夹、三种存放方式，都支持

Typora 存图有几种常见布局，工具会自动探测并在报告的 `Layout` 一行告诉你识别结果。不管哪种布局，做法都是同一件事：**把扫描范围内的所有图片列成一张清单，把所有笔记里的所有引用解析成另一张清单，两张相减**。所以「图片存在哪」不需要你告诉它，只有「笔记在哪」需要。

每条引用都按**引用它的那篇笔记**来定基准，依次尝试：该笔记的 `typora-root-url` → 笔记自己所在目录 → 每个笔记文件夹的根 → 每个 `--images` 目录。任意一个能对上磁盘上的文件就算「被引用」——宁可多对上，多余的候选只会保住文件。

**1. 同名 `.assets` 目录**（Typora 默认）—— 直接扫笔记根目录即可：

```bash
typora-pic-cleaner scan ~/Documents/Notes
```

**2. 统一的 `assets/` 或 `images/` 目录** —— 同样只需要笔记根目录，工具做全局比对。这种布局误删风险最高，请认真看上面的「安全须知」。

**3. Typora 偏好设置里的全局图片文件夹**（图片在笔记库之外）—— 用 `--images` 把它一起交给工具：

```bash
typora-pic-cleaner scan ~/Documents/Notes --images ~/Pictures/TyporaImages
```

`--images` 可以重复多次。这些目录只用来找图片，不会在里面找笔记。

**4. 笔记散在好几个互不相干的文件夹里** —— 全部写上，一次扫完：

```bash
typora-pic-cleaner scan ~/Documents/Notes ~/Work/wiki ~/Desktop/临时笔记
```

---

## 能识别的引用写法

漏掉一种写法就等于误删一张图，所以识别范围铺得比较开：

| 写法 | 例子 |
|---|---|
| 标准 Markdown | `![alt](assets/a.png)` |
| 尖括号包裹（含空格） | `![](<my pic.png>)` |
| 带标题 | `![](a.png "caption")` |
| 普通链接指向图片 | `[下载](files/a.gif)` |
| 引用式定义 | `[key]: ./img/a.jpeg` |
| HTML | `<img src="a.png">`、`srcset`、`<video poster>`、`data-src` |
| 内联 CSS | `style="background:url('bg.png')"` |
| YAML front-matter | `cover: assets/c.png`、`list: [a.jpg, "b (2).webp"]` |
| 百分号编码 | `img/%E4%B8%AD%E6%96%87.png` |
| 反斜杠分隔（Windows） | `note.assets\pic.png` |
| 以图片根为准的路径 | `/assets/a.png` |
| 笔记自己声明的图片根 | front-matter 里的 `typora-root-url: ../图床`，此后 `/pics/a.png` 按它解析 |
| `file://` URL | `file:///C:/pics/a.png` |

**不算引用**：`http(s)://` 远程图、`data:` base64、以及**代码块和行内代码里的路径**（那是文档示例，不是活引用）。

还有一些跨平台细节：macOS/Windows 文件系统大小写不敏感，`A.PNG` 和 `a.png` 会被正确视为同一个文件（在大小写敏感的卷上则不会——工具是实测当前卷的行为，不靠平台猜）；笔记不是 UTF-8 时（Windows 上常见 GBK）也能正确解码，不会因为解码错乱漏掉引用。

---

## 常用参数

| 参数 | 作用 |
|---|---|
| `--lang zh` / `--lang en` | 界面语言，默认跟随系统 |
| `--images DIR` | 额外的图片目录，可重复 |
| `--depth N` | `discover` 向下列几层（默认 3） |
| `--paranoid` | 正文里**光是提到**某个文件名也算引用。保留得更多、删得更少，不确定时用它 |
| `--ext .psd` | 把额外的扩展名也当图片，可重复 |
| `--limit 0` | 列出全部（默认每节最多 50 行） |
| `--json` | 输出机器可读的 JSON |
| `--fail-on-findings` | 发现未引用图片时退出码为 2（CI 里用） |
| `--trash-system` | 移到系统回收站而非笔记库内回收站，需要 `pip install send2trash` |
| `--no-prune` | 保留因清理而变空的文件夹（默认会删掉空目录） |

---

## 开发

分层是：`paths`/`refs` 认引用，`scanner`/`discovery` 找文件，`compare` 做减法，`actions` 负责可撤销的移动，`palette`/`theme`/`folderlist`/`gui` 只管界面。界面里的判断（哪些文件夹要扫、谁被谁包含、勾选怎么记）全在 `discovery.FolderSet` 里，不依赖 Tk，因此能在没有图形界面的 CI 上直接测。

测试只用标准库，直接跑：

```bash
python3 -m unittest discover -s tests -t . -v
```

CI 在 Linux / macOS / Windows × Python 3.9 / 3.13 上跑同一套测试，并把 `ResourceWarning` 当错误处理。

打 `v*` tag 会自动构建并发布 Release：macOS 分 arm64 / x86_64 两种架构，每种都出「窗口版 .app」和「命令行版」；Windows 出对应的两个 exe。发布前会用打包好的产物跑一遍真实扫描做冒烟测试，确认产物本身可用、且 zip 里的执行权限没丢。

## License

Apache License 2.0
