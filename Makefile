CSV ?= demo/MyEBirdData.csv
TAX ?= demo/taxonomy.csv
OUT ?= dashboard
SITE ?= docs
PY  ?= python3

.PHONY: all site dashboard demo clean

all: site

# 生成仪表盘(默认用合成演示数据;换自己的数据见 README)
dashboard:
	$(PY) ebird_dashboard.py $(CSV) -o $(OUT) --taxonomy $(TAX)

# 生成 GitHub Pages 站点:docs/index.html
site: dashboard
	cp $(OUT)/dashboard.html $(SITE)/index.html
	touch $(SITE)/.nojekyll
	@echo "站点已更新: $(SITE)/index.html(直接打开或提交后由 Pages 发布)"

# 重新生成合成演示数据
demo:
	$(PY) tools/make_demo.py
	@echo "演示数据已更新,记得 make site 刷新页面"

clean:
	rm -rf $(OUT)
