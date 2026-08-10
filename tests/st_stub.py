"""Streamlit stub that returns real widget defaults, so app code paths execute."""
import sys
import types

charts = []
messages = []
tables = []


def reset():
    charts.clear()
    messages.clear()
    tables.clear()


def _noop(*a, **k):
    return None


class _Ctx:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def __getattr__(self, name):
        return _noop


def _selectbox(label, options, index=0, **k):
    opts = list(options)
    return opts[index] if opts else None


def _segmented(label, options, default=None, **k):
    opts = list(options)
    return default if default is not None else (opts[0] if opts else None)


def _radio(label, options, **k):
    return list(options)[0]


def _toggle(label, value=False, **k):
    return value


def _plotly_chart(fig, **k):
    charts.append(fig)


def _dataframe(df, **k):
    tables.append(df)


def _record(kind):
    def inner(msg, *a, **k):
        messages.append((kind, str(msg)[:160]))
    return inner


stub = None


def install():
    global stub
    stub = types.ModuleType("streamlit")
    for fn in ["set_page_config", "title", "divider", "write", "markdown", "metric",
               "header", "subheader", "checkbox", "button", "text_input",
               "file_uploader", "spinner", "text_area", "code"]:
        setattr(stub, fn, _noop)

    stub.caption = _record("CAPTION")
    stub.warning = _record("WARN")
    stub.info = _record("INFO")
    stub.error = _record("ERROR")
    stub.success = _record("OK")
    stub.selectbox = _selectbox
    stub.segmented_control = _segmented
    stub.radio = _radio
    stub.toggle = _toggle
    stub.plotly_chart = _plotly_chart
    stub.dataframe = _dataframe
    stub.columns = lambda spec, **k: [_Ctx() for _ in range(spec if isinstance(spec, int) else len(spec))]
    stub.tabs = lambda labels, **k: [_Ctx() for _ in labels]
    stub.expander = lambda label, **k: _Ctx()
    stub.container = lambda **k: _Ctx()
    stub.multiselect = lambda label, options, default=None, **k: list(default if default is not None else options)
    stub.sidebar = types.SimpleNamespace(header=_noop, selectbox=_selectbox, success=_noop,
                                         error=_noop, toggle=_toggle, checkbox=_toggle,
                                         caption=_noop, markdown=_noop, divider=_noop,
                                         button=_noop, write=_noop, info=_noop)
    stub.stop = _noop
    # app.py is gated behind login, so tests run as an already-signed-in user.
    stub.session_state = {"auth_user": {"id": 1, "name": "Test User", "email": "test@example.com"}}
    stub.secrets = {}
    stub.form = lambda *a, **k: _Ctx()
    stub.form_submit_button = lambda *a, **k: False
    stub.cache_data = lambda **k: (lambda f: f)
    stub.date_input = lambda label, value=None, **k: value
    stub.download_button = _noop
    stub.slider = lambda label, lo=0, hi=100, default=None, **k: (default if default is not None else lo)
    sys.modules["streamlit"] = stub
    return stub
