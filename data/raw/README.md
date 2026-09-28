# data/raw 语料目录

## 仓库中的示例
- `sample-anxin-2024.json` / `sample-kangjian-2024.json`：**合成的示例条款**，仅用于跑通链路，**不是真实产品**。

你自己转换或上传的条款只保存在本机 `data/raw/`，默认被 `.gitignore` 和 `.dockerignore` 排除，避免未经确认就把合同文本放进公开仓库或镜像。项目维护者可在 `docs/09-平安2026团体条款入库记录.md` 查看本地处理记录；实际条款 JSON 不随仓库分发。

## 替换成真实语料
1. 到保险公司官网或中国保险行业协会产品库下载条款 PDF，并确认有权在目标环境使用/分享
2. 先运行 `python scripts/ingest.py "条款.pdf" --dry-run` 检查章节识别，再不带 `--dry-run` 写成结构化 JSON
3. **同步修改 `eval/testset.csv` 里的 expected_doc_ids 和 expected_articles**
4. 运行 `python scripts/build_index.py --rebuild`

> 保留 JSON 格式而非直接用 PDF 的原因：真实条款里表格极多，PDF 抽出来的文本是错乱的。先把语料质量和解析难度解耦，链路跑通后再回头啃 PDF 解析。
