// KanzonasPDF's Windows Explorer handlers (KanzonasPDFShell.dll, installed beside KanzonasPDF.exe):
//
//  - a thumbnail handler (IThumbnailProvider): a PDF's first page as its picture in Explorer's
//    folders, instead of the program's icon;
//  - a preview handler (IPreviewHandler): its pages in Explorer's Preview pane (Alt+P), scrolled
//    with the wheel, the scroll bar or the keys.
//
// Both draw with the MuPDF that KanzonasPDF itself uses: PyMuPDF's mupdfcpp64.dll in the
// program's _internal\pymupdf folder (loaded from there on first use, with the C++ runtime
// beside it), through MuPDF's C++ "ll_" functions, which throw a C++ exception on an error.
// So a security update of PyMuPDF updates these too.
//
// Windows runs them outside Explorer (thumbnails in a dllhost.exe, previews in prevhost.exe),
// so a PDF that breaks MuPDF can't take Explorer down. They read the file from the stream
// Explorer gives (IInitializeWithStream: no file path, nothing written), refuse files over
// MAX_BYTES, and a PDF with a password shows the program's icon (thumbnail) or a note (preview).
//
// Built by shell_ext/build.ps1 (MSVC, the static C++ runtime: Explorer's helper processes load
// it before anything of ours could put the runtime on their path). Tested on the Windows build
// machine by shell_ext/kzshell_test.cpp.

#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <ole2.h>
#include <shlwapi.h>
#include <shobjidl.h>
#include <thumbcache.h>
#include <propsys.h>

#include <algorithm>
#include <cstdlib>
#include <map>
#include <new>
#include <string>
#include <vector>

#include "mupdf/functions.h"
#include "kzshell.h"

namespace {

HMODULE g_module = nullptr;
volatile LONG g_objects = 0;        // live objects and factory locks (DllCanUnloadNow)
const ULONGLONG MAX_BYTES = 512ull * 1024 * 1024;
const int MAX_PAGES = 2000;          // the preview lists at most this many pages

// ---- MuPDF, from the program's own folder ---------------------------------------------------

INIT_ONCE g_mupdf_once = INIT_ONCE_STATIC_INIT;
bool g_mupdf_ok = false;

std::wstring module_dir() {
    wchar_t path[MAX_PATH * 2] = {0};
    DWORD n = GetModuleFileNameW(g_module, path, (DWORD)(sizeof(path) / sizeof(path[0])));
    if (n == 0 || n >= sizeof(path) / sizeof(path[0]))
        return std::wstring();
    PathRemoveFileSpecW(path);
    return path;
}

bool exists(const std::wstring &p) {
    return GetFileAttributesW(p.c_str()) != INVALID_FILE_ATTRIBUTES;
}

BOOL CALLBACK load_mupdf(PINIT_ONCE, PVOID, PVOID *) {
    std::wstring dir = module_dir();
    if (dir.empty())
        return TRUE;
    std::wstring internal = dir + L"\\_internal\\";
    // mupdfcpp64.dll needs the Visual C++ runtime: Windows' own when it has one, else the
    // copy the program ships beside it (loaded by full path, then found by name)
    const wchar_t *runtimes[] = {L"vcruntime140.dll", L"vcruntime140_1.dll", L"msvcp140.dll"};
    for (const wchar_t *r : runtimes) {
        if (GetModuleHandleW(r))
            continue;
        if (LoadLibraryExW(r, nullptr, LOAD_LIBRARY_SEARCH_SYSTEM32))
            continue;
        std::wstring own = internal + r;
        if (exists(own))
            LoadLibraryExW(own.c_str(), nullptr, LOAD_WITH_ALTERED_SEARCH_PATH);
    }
    // (where PyInstaller puts it: beside PyMuPDF's own files, or else with the other DLLs)
    const wchar_t *places[] = {L"pymupdf\\mupdfcpp64.dll", L"mupdfcpp64.dll"};
    for (const wchar_t *p : places) {
        std::wstring mu = internal + p;
        if (exists(mu) && LoadLibraryExW(mu.c_str(), nullptr, LOAD_WITH_ALTERED_SEARCH_PATH)) {
            g_mupdf_ok = true;      // (the delay-load helper then finds it by its name)
            break;
        }
    }
    return TRUE;
}

bool mupdf_ready() {
    InitOnceExecuteOnce(&g_mupdf_once, load_mupdf, nullptr, nullptr);
    return g_mupdf_ok;
}

// ---- a PDF read from Explorer's stream ------------------------------------------------------

HRESULT read_stream(IStream *stream, std::vector<unsigned char> &out) {
    out.clear();
    STATSTG st = {};
    if (SUCCEEDED(stream->Stat(&st, STATFLAG_NONAME))) {
        if (st.cbSize.QuadPart > MAX_BYTES)
            return E_OUTOFMEMORY;
        try {
            out.reserve((size_t)st.cbSize.QuadPart);
        } catch (...) {
            return E_OUTOFMEMORY;
        }
    }
    unsigned char buf[1 << 16];
    for (;;) {
        ULONG got = 0;
        HRESULT hr = stream->Read(buf, sizeof(buf), &got);
        if (FAILED(hr))
            return hr;
        if (got == 0)
            break;
        if (out.size() + got > MAX_BYTES)
            return E_OUTOFMEMORY;
        try {
            out.insert(out.end(), buf, buf + got);
        } catch (...) {
            return E_OUTOFMEMORY;
        }
        if (hr == S_FALSE)
            break;
    }
    return out.empty() ? E_FAIL : S_OK;
}

enum class Opened { ok, failed, password };

struct Pdf {
    std::vector<unsigned char> data;
    fz_stream *stm = nullptr;
    fz_document *doc = nullptr;

    ~Pdf() { close(); }

    Opened open() {
        close();
        if (data.empty() || !mupdf_ready())
            return Opened::failed;
        try {
            stm = mupdf::ll_fz_open_memory(data.data(), data.size());
            doc = mupdf::ll_fz_open_document_with_stream("application/pdf", stm);
            if (mupdf::ll_fz_needs_password(doc) &&
                    !mupdf::ll_fz_authenticate_password(doc, "")) {
                close();
                return Opened::password;
            }
            if (mupdf::ll_fz_count_pages(doc) < 1) {
                close();
                return Opened::failed;
            }
        } catch (...) {
            close();
            return Opened::failed;
        }
        return Opened::ok;
    }

    void close() {
        if (doc) {
            try { mupdf::ll_fz_drop_document(doc); } catch (...) {}
            doc = nullptr;
        }
        if (stm) {
            try { mupdf::ll_fz_drop_stream(stm); } catch (...) {}
            stm = nullptr;
        }
    }
};

// A page drawn (annotations included, on white) as a top-down 32-bit bitmap, scale pixels per
// point; nullptr when MuPDF can't draw it.
HBITMAP draw_page(fz_document *doc, int number, float scale, int *w_out, int *h_out) {
    fz_page *page = nullptr;
    fz_pixmap *pix = nullptr;
    HBITMAP bmp = nullptr;
    try {
        page = mupdf::ll_fz_load_page(doc, number);
        fz_matrix m = {scale, 0, 0, scale, 0, 0};
        pix = mupdf::ll_fz_new_pixmap_from_page(page, m, mupdf::ll_fz_device_rgb(), 0);
        int w = mupdf::ll_fz_pixmap_width(pix), h = mupdf::ll_fz_pixmap_height(pix);
        int n = mupdf::ll_fz_pixmap_components(pix);
        int stride = mupdf::ll_fz_pixmap_stride(pix);
        const unsigned char *src = mupdf::ll_fz_pixmap_samples(pix);
        if (w > 0 && h > 0 && n >= 3 && src) {
            BITMAPINFO bi = {};
            bi.bmiHeader.biSize = sizeof(bi.bmiHeader);
            bi.bmiHeader.biWidth = w;
            bi.bmiHeader.biHeight = -h;             // (top-down)
            bi.bmiHeader.biPlanes = 1;
            bi.bmiHeader.biBitCount = 32;
            bi.bmiHeader.biCompression = BI_RGB;
            void *bits = nullptr;
            bmp = CreateDIBSection(nullptr, &bi, DIB_RGB_COLORS, &bits, nullptr, 0);
            if (bmp && bits) {
                unsigned char *dst = (unsigned char *)bits;
                for (int y = 0; y < h; y++) {
                    const unsigned char *s = src + (size_t)y * stride;
                    unsigned char *d = dst + (size_t)y * w * 4;
                    for (int x = 0; x < w; x++, s += n, d += 4) {
                        d[0] = s[2];
                        d[1] = s[1];
                        d[2] = s[0];
                        d[3] = 255;
                    }
                }
                if (w_out) *w_out = w;
                if (h_out) *h_out = h;
            } else if (bmp) {
                DeleteObject(bmp);
                bmp = nullptr;
            }
        }
    } catch (...) {
        if (bmp) {
            DeleteObject(bmp);
            bmp = nullptr;
        }
    }
    if (pix) { try { mupdf::ll_fz_drop_pixmap(pix); } catch (...) {} }
    if (page) { try { mupdf::ll_fz_drop_page(page); } catch (...) {} }
    return bmp;
}

bool page_size(fz_document *doc, int number, float *w, float *h) {
    fz_page *page = nullptr;
    bool ok = false;
    try {
        page = mupdf::ll_fz_load_page(doc, number);
        fz_rect r = mupdf::ll_fz_bound_page(page);
        *w = r.x1 - r.x0;
        *h = r.y1 - r.y0;
        ok = *w > 0 && *h > 0;
    } catch (...) {
    }
    if (page) { try { mupdf::ll_fz_drop_page(page); } catch (...) {} }
    return ok;
}

// ---- the texts the preview shows, in the user's language (as the program's) -----------------

const wchar_t *text(int which) {
    // 0: protected with a password; 1: can't be shown
    LANGID lang = PRIMARYLANGID(GetUserDefaultUILanguage());
    if (lang == LANG_SPANISH)
        return which == 0 ? L"Este PDF está protegido con una contraseña: ábralo en KanzonasPDF."
                          : L"No se puede mostrar este PDF.";
    if (lang == LANG_ITALIAN)
        return which == 0 ? L"Questo PDF è protetto da una password: aprilo in KanzonasPDF."
                          : L"Impossibile mostrare questo PDF.";
    return which == 0 ? L"This PDF is protected with a password: open it in KanzonasPDF."
                      : L"This PDF can't be shown.";
}

// ---- the thumbnail handler ------------------------------------------------------------------

class Thumbnail : public IInitializeWithStream, public IThumbnailProvider {
    LONG refs_ = 1;
    Pdf pdf_;

public:
    Thumbnail() { InterlockedIncrement(&g_objects); }
    virtual ~Thumbnail() { InterlockedDecrement(&g_objects); }

    IFACEMETHODIMP QueryInterface(REFIID riid, void **ppv) override {
        static const QITAB qit[] = {
            QITABENT(Thumbnail, IInitializeWithStream),
            QITABENT(Thumbnail, IThumbnailProvider),
            {0},
        };
        return QISearch(this, qit, riid, ppv);
    }
    IFACEMETHODIMP_(ULONG) AddRef() override { return InterlockedIncrement(&refs_); }
    IFACEMETHODIMP_(ULONG) Release() override {
        LONG n = InterlockedDecrement(&refs_);
        if (n == 0)
            delete this;
        return n;
    }

    IFACEMETHODIMP Initialize(IStream *stream, DWORD) override {
        if (!stream)
            return E_INVALIDARG;
        if (!pdf_.data.empty())
            return HRESULT_FROM_WIN32(ERROR_ALREADY_INITIALIZED);
        return read_stream(stream, pdf_.data);
    }

    IFACEMETHODIMP GetThumbnail(UINT cx, HBITMAP *phbmp, WTS_ALPHATYPE *alpha) override {
        if (!phbmp)
            return E_POINTER;
        *phbmp = nullptr;
        if (alpha)
            *alpha = WTSAT_RGB;
        if (cx == 0 || cx > 4096)
            return E_INVALIDARG;
        if (pdf_.open() != Opened::ok)
            return E_FAIL;              // (Explorer shows the program's icon)
        float w = 0, h = 0;
        HBITMAP bmp = nullptr;
        if (page_size(pdf_.doc, 0, &w, &h)) {
            float scale = (float)cx / std::max(w, h);
            bmp = draw_page(pdf_.doc, 0, scale, nullptr, nullptr);
        }
        pdf_.close();
        if (!bmp)
            return E_FAIL;
        *phbmp = bmp;
        return S_OK;
    }
};

// ---- the preview handler --------------------------------------------------------------------

const wchar_t PREVIEW_CLASS[] = L"KanzonasPDFPreview";
const int MARGIN = 8, GAP = 8, LINE = 40;

class Preview : public IPreviewHandler, public IInitializeWithStream, public IObjectWithSite,
                public IOleWindow {
    LONG refs_ = 1;
    IUnknown *site_ = nullptr;
    HWND parent_ = nullptr, hwnd_ = nullptr;
    RECT rect_ = {};
    Pdf pdf_;
    Opened opened_ = Opened::failed;
    std::vector<float> pw_, ph_;            // page sizes, points
    std::vector<int> top_, height_;         // layout for the window's width, pixels
    int layout_width_ = -1, total_ = 0, scroll_ = 0;
    struct Drawn { HBITMAP bmp; int w, h; };
    std::map<int, Drawn> cache_;            // pages drawn for layout_width_

public:
    Preview() { InterlockedIncrement(&g_objects); }
    virtual ~Preview() {
        Unload();
        if (site_)
            site_->Release();
        InterlockedDecrement(&g_objects);
    }

    IFACEMETHODIMP QueryInterface(REFIID riid, void **ppv) override {
        static const QITAB qit[] = {
            QITABENT(Preview, IPreviewHandler),
            QITABENT(Preview, IInitializeWithStream),
            QITABENT(Preview, IObjectWithSite),
            QITABENT(Preview, IOleWindow),
            {0},
        };
        return QISearch(this, qit, riid, ppv);
    }
    IFACEMETHODIMP_(ULONG) AddRef() override { return InterlockedIncrement(&refs_); }
    IFACEMETHODIMP_(ULONG) Release() override {
        LONG n = InterlockedDecrement(&refs_);
        if (n == 0)
            delete this;
        return n;
    }

    // IInitializeWithStream
    IFACEMETHODIMP Initialize(IStream *stream, DWORD) override {
        if (!stream)
            return E_INVALIDARG;
        return read_stream(stream, pdf_.data);
    }

    // IObjectWithSite
    IFACEMETHODIMP SetSite(IUnknown *site) override {
        if (site_)
            site_->Release();
        site_ = site;
        if (site_)
            site_->AddRef();
        return S_OK;
    }
    IFACEMETHODIMP GetSite(REFIID riid, void **ppv) override {
        if (!ppv)
            return E_POINTER;
        *ppv = nullptr;
        return site_ ? site_->QueryInterface(riid, ppv) : E_FAIL;
    }

    // IOleWindow
    IFACEMETHODIMP GetWindow(HWND *phwnd) override {
        if (!phwnd)
            return E_INVALIDARG;
        *phwnd = parent_;
        return S_OK;
    }
    IFACEMETHODIMP ContextSensitiveHelp(BOOL) override { return E_NOTIMPL; }

    // IPreviewHandler
    IFACEMETHODIMP SetWindow(HWND hwnd, const RECT *prc) override {
        if (!hwnd || !prc)
            return E_INVALIDARG;
        parent_ = hwnd;
        rect_ = *prc;
        if (hwnd_) {
            SetParent(hwnd_, parent_);
            place();
        }
        return S_OK;
    }
    IFACEMETHODIMP SetRect(const RECT *prc) override {
        if (!prc)
            return E_INVALIDARG;
        rect_ = *prc;
        if (hwnd_)
            place();
        return S_OK;
    }
    IFACEMETHODIMP DoPreview() override {
        if (hwnd_)
            return S_OK;
        if (!parent_)
            return E_FAIL;
        if (!register_class())
            return HRESULT_FROM_WIN32(GetLastError());
        opened_ = pdf_.open();
        if (opened_ == Opened::ok) {
            int n = 0;
            try { n = mupdf::ll_fz_count_pages(pdf_.doc); } catch (...) { n = 0; }
            n = std::min(n, MAX_PAGES);
            for (int i = 0; i < n; i++) {
                float w = 0, h = 0;
                if (!page_size(pdf_.doc, i, &w, &h)) {
                    w = pw_.empty() ? 612.0f : pw_.back();  // (a page MuPDF can't read: a
                    h = ph_.empty() ? 792.0f : ph_.back();  // blank of its neighbor's size)
                }
                pw_.push_back(w);
                ph_.push_back(h);
            }
            if (pw_.empty())
                opened_ = Opened::failed;
        }
        hwnd_ = CreateWindowExW(0, PREVIEW_CLASS, L"", WS_CHILD | WS_VISIBLE | WS_VSCROLL,
                                rect_.left, rect_.top, rect_.right - rect_.left,
                                rect_.bottom - rect_.top, parent_, nullptr, g_module, this);
        if (!hwnd_)
            return HRESULT_FROM_WIN32(GetLastError());
        relayout();
        return S_OK;
    }
    IFACEMETHODIMP Unload() override {
        if (hwnd_) {
            HWND h = hwnd_;
            hwnd_ = nullptr;
            SetWindowLongPtrW(h, GWLP_USERDATA, 0);
            DestroyWindow(h);
        }
        drop_cache();
        pw_.clear();
        ph_.clear();
        top_.clear();
        height_.clear();
        layout_width_ = -1;
        pdf_.close();
        pdf_.data.clear();
        pdf_.data.shrink_to_fit();
        return S_OK;
    }
    IFACEMETHODIMP SetFocus() override {
        if (hwnd_)
            ::SetFocus(hwnd_);
        return S_OK;
    }
    IFACEMETHODIMP QueryFocus(HWND *phwnd) override {
        if (!phwnd)
            return E_INVALIDARG;
        *phwnd = ::GetFocus();
        return *phwnd ? S_OK : HRESULT_FROM_WIN32(GetLastError());
    }
    IFACEMETHODIMP TranslateAccelerator(MSG *msg) override {
        // (keys the preview doesn't use go to Explorer, as its frame asks)
        HRESULT hr = S_FALSE;
        IPreviewHandlerFrame *frame = nullptr;
        if (site_ && SUCCEEDED(site_->QueryInterface(IID_PPV_ARGS(&frame)))) {
            hr = frame->TranslateAccelerator(msg);
            frame->Release();
        }
        return hr;
    }

    static LRESULT CALLBACK proc(HWND hwnd, UINT msg, WPARAM wp, LPARAM lp) {
        if (msg == WM_NCCREATE) {
            auto *cs = (CREATESTRUCTW *)lp;
            SetWindowLongPtrW(hwnd, GWLP_USERDATA, (LONG_PTR)cs->lpCreateParams);
        }
        auto *self = (Preview *)GetWindowLongPtrW(hwnd, GWLP_USERDATA);
        if (self) {
            LRESULT r = 0;
            if (self->handle(hwnd, msg, wp, lp, &r))
                return r;
        }
        return DefWindowProcW(hwnd, msg, wp, lp);
    }

private:
    static bool register_class() {
        WNDCLASSEXW wc = {};
        wc.cbSize = sizeof(wc);
        if (GetClassInfoExW(g_module, PREVIEW_CLASS, &wc))
            return true;
        wc.cbSize = sizeof(wc);
        wc.style = CS_HREDRAW | CS_VREDRAW;
        wc.lpfnWndProc = proc;
        wc.hInstance = g_module;
        wc.hCursor = LoadCursor(nullptr, IDC_ARROW);
        wc.hbrBackground = nullptr;
        wc.lpszClassName = PREVIEW_CLASS;
        return RegisterClassExW(&wc) != 0 || GetLastError() == ERROR_CLASS_ALREADY_EXISTS;
    }

    void place() {
        SetWindowPos(hwnd_, nullptr, rect_.left, rect_.top, rect_.right - rect_.left,
                     rect_.bottom - rect_.top, SWP_NOZORDER | SWP_NOACTIVATE);
        relayout();
    }

    void drop_cache() {
        for (auto &kv : cache_)
            DeleteObject(kv.second.bmp);
        cache_.clear();
    }

    int client_width() {
        RECT rc = {};
        GetClientRect(hwnd_, &rc);
        return rc.right - rc.left;
    }
    int client_height() {
        RECT rc = {};
        GetClientRect(hwnd_, &rc);
        return rc.bottom - rc.top;
    }

    // Each page as wide as the pane (less its margins), one below the other.
    void relayout() {
        if (!hwnd_)
            return;
        int width = client_width();
        if (width != layout_width_) {
            layout_width_ = width;
            drop_cache();
            top_.assign(pw_.size(), 0);
            height_.assign(pw_.size(), 0);
            int y = MARGIN, avail = std::max(1, width - 2 * MARGIN);
            for (size_t i = 0; i < pw_.size(); i++) {
                top_[i] = y;
                height_[i] = std::max(1, (int)(ph_[i] * avail / pw_[i] + 0.5f));
                y += height_[i] + GAP;
            }
            total_ = pw_.empty() ? 0 : y - GAP + MARGIN;
        }
        set_scroll(scroll_);
        InvalidateRect(hwnd_, nullptr, FALSE);
    }

    void set_scroll(int pos) {
        int page = client_height();
        int most = std::max(0, total_ - page);
        scroll_ = std::max(0, std::min(pos, most));
        SCROLLINFO si = {};
        si.cbSize = sizeof(si);
        si.fMask = SIF_RANGE | SIF_PAGE | SIF_POS | SIF_DISABLENOSCROLL;
        si.nMin = 0;
        si.nMax = std::max(0, total_ - 1);
        si.nPage = (UINT)std::max(0, page);
        si.nPos = scroll_;
        SetScrollInfo(hwnd_, SB_VERT, &si, TRUE);
    }

    void scroll_to(int pos) {
        int was = scroll_;
        set_scroll(pos);
        if (scroll_ != was)
            InvalidateRect(hwnd_, nullptr, FALSE);
    }

    const Drawn *drawn(int i) {
        auto it = cache_.find(i);
        if (it != cache_.end())
            return &it->second;
        // (only the pages near the ones shown are kept)
        while (cache_.size() >= 12) {
            auto victim = std::max_element(cache_.begin(), cache_.end(),
                [i](const std::pair<const int, Drawn> &a, const std::pair<const int, Drawn> &b) {
                    return std::abs(a.first - i) < std::abs(b.first - i);
                });
            DeleteObject(victim->second.bmp);
            cache_.erase(victim);
        }
        int avail = std::max(1, layout_width_ - 2 * MARGIN);
        Drawn d = {nullptr, 0, 0};
        d.bmp = draw_page(pdf_.doc, i, avail / pw_[i], &d.w, &d.h);
        if (!d.bmp)
            return nullptr;
        return &(cache_[i] = d);
    }

    void paint(HDC hdc) {
        RECT rc = {};
        GetClientRect(hwnd_, &rc);
        HBRUSH back = CreateSolidBrush(RGB(0xE6, 0xE6, 0xE6));
        FillRect(hdc, &rc, back);
        DeleteObject(back);
        if (opened_ != Opened::ok) {
            RECT box = rc;
            InflateRect(&box, -16, -16);
            SetBkMode(hdc, TRANSPARENT);
            SetTextColor(hdc, RGB(0x20, 0x20, 0x20));
            HFONT font = (HFONT)GetStockObject(DEFAULT_GUI_FONT);
            HGDIOBJ old = SelectObject(hdc, font);
            DrawTextW(hdc, text(opened_ == Opened::password ? 0 : 1), -1, &box,
                      DT_CENTER | DT_WORDBREAK | DT_NOPREFIX);
            SelectObject(hdc, old);
            return;
        }
        HDC mem = CreateCompatibleDC(hdc);
        for (size_t i = 0; i < top_.size(); i++) {
            int y = top_[i] - scroll_;
            if (y + height_[i] < rc.top)
                continue;
            if (y > rc.bottom)
                break;
            RECT page = {MARGIN, y, MARGIN + std::max(1, layout_width_ - 2 * MARGIN),
                         y + height_[i]};
            const Drawn *d = drawn((int)i);
            if (d) {
                HGDIOBJ old = SelectObject(mem, d->bmp);
                BitBlt(hdc, page.left, page.top, d->w, d->h, mem, 0, 0, SRCCOPY);
                SelectObject(mem, old);
            } else {
                FillRect(hdc, &page, (HBRUSH)GetStockObject(WHITE_BRUSH));
            }
        }
        DeleteDC(mem);
    }

    bool handle(HWND hwnd, UINT msg, WPARAM wp, LPARAM lp, LRESULT *r) {
        switch (msg) {
        case WM_PAINT: {
            PAINTSTRUCT ps;
            HDC hdc = BeginPaint(hwnd, &ps);
            // (drawn off screen, then shown at once: no flicker while scrolling)
            RECT rc = {};
            GetClientRect(hwnd, &rc);
            HDC buf = CreateCompatibleDC(hdc);
            HBITMAP bmp = CreateCompatibleBitmap(hdc, std::max(1L, rc.right), std::max(1L, rc.bottom));
            HGDIOBJ old = SelectObject(buf, bmp);
            paint(buf);
            BitBlt(hdc, 0, 0, rc.right, rc.bottom, buf, 0, 0, SRCCOPY);
            SelectObject(buf, old);
            DeleteObject(bmp);
            DeleteDC(buf);
            EndPaint(hwnd, &ps);
            return true;
        }
        case WM_PRINTCLIENT:
            paint((HDC)wp);
            return true;
        case WM_ERASEBKGND:
            *r = 1;
            return true;
        case WM_SIZE:
            relayout();
            return true;
        case WM_VSCROLL: {
            SCROLLINFO si = {};
            si.cbSize = sizeof(si);
            si.fMask = SIF_TRACKPOS;
            GetScrollInfo(hwnd, SB_VERT, &si);
            int page = client_height();
            switch (LOWORD(wp)) {
            case SB_LINEUP: scroll_to(scroll_ - LINE); break;
            case SB_LINEDOWN: scroll_to(scroll_ + LINE); break;
            case SB_PAGEUP: scroll_to(scroll_ - page); break;
            case SB_PAGEDOWN: scroll_to(scroll_ + page); break;
            case SB_TOP: scroll_to(0); break;
            case SB_BOTTOM: scroll_to(total_); break;
            case SB_THUMBTRACK:
            case SB_THUMBPOSITION: scroll_to(si.nTrackPos); break;
            }
            return true;
        }
        case WM_MOUSEWHEEL: {
            int delta = GET_WHEEL_DELTA_WPARAM(wp);
            UINT lines = 3;
            SystemParametersInfoW(SPI_GETWHEELSCROLLLINES, 0, &lines, 0);
            if (lines == WHEEL_PAGESCROLL)
                scroll_to(scroll_ - (delta > 0 ? 1 : -1) * client_height());
            else
                scroll_to(scroll_ - delta * (int)lines * LINE / WHEEL_DELTA);   // (a line a notch)
            return true;
        }
        case WM_KEYDOWN:
            switch (wp) {
            case VK_UP: scroll_to(scroll_ - LINE); return true;
            case VK_DOWN: scroll_to(scroll_ + LINE); return true;
            case VK_PRIOR: scroll_to(scroll_ - client_height()); return true;
            case VK_NEXT: case VK_SPACE: scroll_to(scroll_ + client_height()); return true;
            case VK_HOME: scroll_to(0); return true;
            case VK_END: scroll_to(total_); return true;
            }
            return false;
        case WM_LBUTTONDOWN:
            ::SetFocus(hwnd);
            return true;
        case WM_NCDESTROY:
            SetWindowLongPtrW(hwnd, GWLP_USERDATA, 0);
            if (hwnd_ == hwnd)
                hwnd_ = nullptr;
            return false;
        }
        (void)lp;
        return false;
    }
};

// ---- the class factory ----------------------------------------------------------------------

template <class T>
class Factory : public IClassFactory {
    LONG refs_ = 1;

public:
    virtual ~Factory() {}
    IFACEMETHODIMP QueryInterface(REFIID riid, void **ppv) override {
        static const QITAB qit[] = {QITABENT(Factory, IClassFactory), {0}};
        return QISearch(this, qit, riid, ppv);
    }
    IFACEMETHODIMP_(ULONG) AddRef() override { return InterlockedIncrement(&refs_); }
    IFACEMETHODIMP_(ULONG) Release() override {
        LONG n = InterlockedDecrement(&refs_);
        if (n == 0)
            delete this;
        return n;
    }
    IFACEMETHODIMP CreateInstance(IUnknown *outer, REFIID riid, void **ppv) override {
        if (!ppv)
            return E_POINTER;
        *ppv = nullptr;
        if (outer)
            return CLASS_E_NOAGGREGATION;
        T *obj = new (std::nothrow) T();
        if (!obj)
            return E_OUTOFMEMORY;
        HRESULT hr = obj->QueryInterface(riid, ppv);
        obj->Release();
        return hr;
    }
    IFACEMETHODIMP LockServer(BOOL lock) override {
        if (lock)
            InterlockedIncrement(&g_objects);
        else
            InterlockedDecrement(&g_objects);
        return S_OK;
    }
};

}  // namespace

// ---- what the DLL exports -------------------------------------------------------------------

BOOL APIENTRY DllMain(HMODULE module, DWORD reason, LPVOID) {
    if (reason == DLL_PROCESS_ATTACH) {
        g_module = module;
        DisableThreadLibraryCalls(module);
    }
    return TRUE;
}

STDAPI DllGetClassObject(REFCLSID clsid, REFIID riid, void **ppv) {
    if (!ppv)
        return E_POINTER;
    *ppv = nullptr;
    IClassFactory *f = nullptr;
    if (IsEqualCLSID(clsid, CLSID_KzThumbnail))
        f = new (std::nothrow) Factory<Thumbnail>();
    else if (IsEqualCLSID(clsid, CLSID_KzPreview))
        f = new (std::nothrow) Factory<Preview>();
    else
        return CLASS_E_CLASSNOTAVAILABLE;
    if (!f)
        return E_OUTOFMEMORY;
    HRESULT hr = f->QueryInterface(riid, ppv);
    f->Release();
    return hr;
}

STDAPI DllCanUnloadNow() {
    // (MuPDF stays loaded once used: unloading it under a thread that used it isn't safe)
    return g_objects == 0 && !g_mupdf_ok ? S_OK : S_FALSE;
}
