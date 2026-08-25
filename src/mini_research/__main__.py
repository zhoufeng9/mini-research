"""让项目支持通过 ``python -m mini_research`` 启动。"""

from mini_research.app import main

if __name__ == "__main__":
    raise SystemExit(main())
