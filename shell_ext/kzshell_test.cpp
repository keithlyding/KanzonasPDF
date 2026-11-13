// Tests KanzonasPDFShell.dll as Explorer uses it, on the Windows build machine
// (.github/workflows/build-windows.yml, after shell_ext/build.ps1):
//
//   kzshell_test.exe <KanzonasPDFShell.dll> <dir>
//
// <dir> holds the PDFs tests/make_shell_ext_pdfs.py made: page.pdf (a black box on a white
// page), two.pdf (two pages), locked.pdf (a password), wide.pdf (a landscape page), and
// garbage.pdf (not a PDF). The handlers are made through the DLL's own class factory (as COM
// makes them for Explorer) and given each file as a stream; thumb.bmp and preview.bmp are
// written there to look at. Exit code 0 when every check passes.

#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <ole2.h>
#include <shlwapi.h>
#include <shobjidl.h>
#include <thumbcache.h>
#include <propsys.h>

#include <cstdio>
#include <string>

#include "kzshell.h"

typedef HRESULT(STDAPICALLTYPE *GetClassObject)(REFCLSID, REFIID, void **);

static int failures = 0;

static void check(bool ok, const char *what) {
    std::printf("%s %s\n", ok ? "PASS" : "FAIL", what);
    std::fflush(stdout);
    if (!ok)
        failures++;
}

static IStream *open_stream(const std::wstring &path) {
    IStream *s = nullptr;
    if (FAILED(SHCreateStreamOnFileEx(path.c_str(), STGM_READ | STGM_SHARE_DENY_NONE, 0, FALSE,
                                      nullptr, &s)))
        return nullptr;
    return s;
}

template <class T>
static T *make(GetClassObject get, REFCLSID clsid) {
    IClassFactory *f = nullptr;
    if (FAILED(get(clsid, IID_PPV_ARGS(&f))))
        return nullptr;
    T *obj = nullptr;
    HRESULT hr = f->CreateInstance(nullptr, __uuidof(T), (void **)&obj);
    f->Release();
    return SUCCEEDED(hr) ? obj : nullptr;
}

// The 32-bit pixels of a bitmap, and how many are dark.
static int dark_pixels(HBITMAP bmp, int *w, int *h) {
    BITMAP bm = {};
    GetObject(bmp, sizeof(bm), &bm);
    *w = bm.bmWidth;
    *h = bm.bmHeight < 0 ? -bm.bmHeight : bm.bmHeight;
    BITMAPINFO bi = {};
    bi.bmiHeader.biSize = sizeof(bi.bmiHeader);
    bi.bmiHeader.biWidth = *w;
    bi.bmiHeader.biHeight = -*h;
    bi.bmiHeader.biPlanes = 1;
    bi.bmiHeader.biBitCount = 32;
    bi.bmiHeader.biCompression = BI_RGB;
    std::string px((size_t)*w * *h * 4, '\0');
    HDC dc = GetDC(nullptr);
    GetDIBits(dc, bmp, 0, *h, &px[0], &bi, DIB_RGB_COLORS);
    ReleaseDC(nullptr, dc);
    int dark = 0;
    for (size_t i = 0; i + 3 < px.size(); i += 4)
        if ((unsigned char)px[i] < 80 && (unsigned char)px[i + 1] < 80 &&
            (unsigned char)px[i + 2] < 80)
            dark++;
    return dark;
}

static void save_bmp(HBITMAP bmp, const std::wstring &path) {
    BITMAP bm = {};
    GetObject(bmp, sizeof(bm), &bm);
    int w = bm.bmWidth, h = bm.bmHeight < 0 ? -bm.bmHeight : bm.bmHeight;
    BITMAPINFOHEADER bih = {};
    bih.biSize = sizeof(bih);
    bih.biWidth = w;
    bih.biHeight = -h;
    bih.biPlanes = 1;
    bih.biBitCount = 32;
    bih.biCompression = BI_RGB;
    std::string px((size_t)w * h * 4, '\0');
    HDC dc = GetDC(nullptr);
    GetDIBits(dc, bmp, 0, h, &px[0], (BITMAPINFO *)&bih, DIB_RGB_COLORS);
    ReleaseDC(nullptr, dc);
    BITMAPFILEHEADER bfh = {};
    bfh.bfType = 0x4D42;
    bfh.bfOffBits = sizeof(bfh) + sizeof(bih);
    bfh.bfSize = (DWORD)(bfh.bfOffBits + px.size());
    FILE *f = _wfopen(path.c_str(), L"wb");
    if (!f)
        return;
    fwrite(&bfh, sizeof(bfh), 1, f);
    fwrite(&bih, sizeof(bih), 1, f);
    fwrite(px.data(), 1, px.size(), f);
    fclose(f);
}

static HRESULT thumbnail(GetClassObject get, const std::wstring &pdf, UINT cx, HBITMAP *out) {
    *out = nullptr;
    IInitializeWithStream *init = make<IInitializeWithStream>(get, CLSID_KzThumbnail);
    if (!init)
        return E_NOINTERFACE;
    IStream *s = open_stream(pdf);
    HRESULT hr = s ? init->Initialize(s, STGM_READ) : E_FAIL;
    if (s)
        s->Release();
    if (SUCCEEDED(hr)) {
        IThumbnailProvider *tp = nullptr;
        hr = init->QueryInterface(IID_PPV_ARGS(&tp));
        if (SUCCEEDED(hr)) {
            WTS_ALPHATYPE alpha = WTSAT_UNKNOWN;
            hr = tp->GetThumbnail(cx, out, &alpha);
            tp->Release();
        }
    }
    init->Release();
    return hr;
}

static LRESULT CALLBACK host_proc(HWND h, UINT m, WPARAM w, LPARAM l) {
    return DefWindowProcW(h, m, w, l);
}

static void pump(int ms) {
    DWORD end = GetTickCount() + ms;
    MSG msg;
    while (GetTickCount() < end) {
        while (PeekMessageW(&msg, nullptr, 0, 0, PM_REMOVE)) {
            TranslateMessage(&msg);
            DispatchMessageW(&msg);
        }
        Sleep(10);
    }
}

// The preview of pdf in a 500 x 700 window: how many dark pixels it shows, and its scroll
// position after a Page Down (-1: no scroll bar).
static bool preview(GetClassObject get, const std::wstring &pdf, HWND host, int *dark,
                    int *scrolled, const std::wstring &shot) {
    *dark = 0;
    *scrolled = -1;
    IPreviewHandler *ph = make<IPreviewHandler>(get, CLSID_KzPreview);
    if (!ph)
        return false;
    IInitializeWithStream *init = nullptr;
    bool ok = SUCCEEDED(ph->QueryInterface(IID_PPV_ARGS(&init)));
    IStream *s = open_stream(pdf);
    ok = ok && s && SUCCEEDED(init->Initialize(s, STGM_READ));
    if (s)
        s->Release();
    if (init)
        init->Release();
    RECT rc = {0, 0, 500, 700};
    ok = ok && SUCCEEDED(ph->SetWindow(host, &rc)) && SUCCEEDED(ph->DoPreview());
    pump(300);
    HWND child = FindWindowExW(host, nullptr, L"KanzonasPDFPreview", nullptr);
    ok = ok && child != nullptr;
    if (child) {
        HDC dc = GetDC(child);
        HDC mem = CreateCompatibleDC(dc);
        HBITMAP bmp = CreateCompatibleBitmap(dc, 500, 700);
        HGDIOBJ old = SelectObject(mem, bmp);
        PrintWindow(child, mem, PW_CLIENTONLY);
        SelectObject(mem, old);
        int w = 0, h = 0;
        *dark = dark_pixels(bmp, &w, &h);
        if (!shot.empty())
            save_bmp(bmp, shot);
        DeleteObject(bmp);
        DeleteDC(mem);
        ReleaseDC(child, dc);
        SendMessageW(child, WM_VSCROLL, SB_PAGEDOWN, 0);
        SCROLLINFO si = {};
        si.cbSize = sizeof(si);
        si.fMask = SIF_POS;
        if (GetScrollInfo(child, SB_VERT, &si))
            *scrolled = si.nPos;
        RECT smaller = {0, 0, 300, 400};
        ok = ok && SUCCEEDED(ph->SetRect(&smaller));
        pump(100);
    }
    ok = ok && SUCCEEDED(ph->Unload());
    pump(100);
    ok = ok && FindWindowExW(host, nullptr, L"KanzonasPDFPreview", nullptr) == nullptr;
    ph->Release();
    return ok;
}

int wmain(int argc, wchar_t **argv) {
    if (argc < 3) {
        std::printf("usage: kzshell_test.exe <KanzonasPDFShell.dll> <dir>\n");
        return 2;
    }
    std::wstring dir = argv[2];
    OleInitialize(nullptr);
    HMODULE dll = LoadLibraryW(argv[1]);
    check(dll != nullptr, "the DLL loads");
    if (!dll)
        return 1;
    auto get = (GetClassObject)GetProcAddress(dll, "DllGetClassObject");
    check(get != nullptr && GetProcAddress(dll, "DllCanUnloadNow") != nullptr,
          "it exports DllGetClassObject and DllCanUnloadNow");
    if (!get)
        return 1;
    IClassFactory *f = nullptr;
    check(get(CLSID_NULL, IID_PPV_ARGS(&f)) == CLASS_E_CLASSNOTAVAILABLE,
          "an unknown class is refused");

    // thumbnails
    HBITMAP bmp = nullptr;
    HRESULT hr = thumbnail(get, dir + L"\\page.pdf", 256, &bmp);
    check(SUCCEEDED(hr) && bmp, "a thumbnail of page.pdf");
    if (bmp) {
        int w = 0, h = 0, dark = dark_pixels(bmp, &w, &h);
        std::printf("     %d x %d, %d dark pixels\n", w, h, dark);
        check(h == 256 && w > 150 && w < 256, "as tall as asked, narrower (a portrait page)");
        check(dark > w * h / 20 && dark < w * h / 2, "the page's black box on white");
        save_bmp(bmp, dir + L"\\thumb.bmp");
        DeleteObject(bmp);
    }
    hr = thumbnail(get, dir + L"\\wide.pdf", 96, &bmp);
    check(SUCCEEDED(hr) && bmp, "a small thumbnail of a landscape page");
    if (bmp) {
        int w = 0, h = 0;
        dark_pixels(bmp, &w, &h);
        check(w == 96 && h < 96, "as wide as asked, lower");
        DeleteObject(bmp);
    }
    hr = thumbnail(get, dir + L"\\locked.pdf", 256, &bmp);
    check(FAILED(hr) && !bmp, "no thumbnail of a PDF with a password (Explorer shows the icon)");
    hr = thumbnail(get, dir + L"\\garbage.pdf", 256, &bmp);
    check(FAILED(hr) && !bmp, "no thumbnail of a file that isn't a PDF");

    // previews
    WNDCLASSW wc = {};
    wc.lpfnWndProc = host_proc;
    wc.hInstance = GetModuleHandleW(nullptr);
    wc.lpszClassName = L"KzTestHost";
    RegisterClassW(&wc);
    HWND host = CreateWindowExW(0, L"KzTestHost", L"preview test", WS_OVERLAPPEDWINDOW | WS_VISIBLE,
                                0, 0, 540, 760, nullptr, nullptr, wc.hInstance, nullptr);
    check(host != nullptr, "a window to preview in");
    int dark = 0, scrolled = -1;
    bool ok = preview(get, dir + L"\\two.pdf", host, &dark, &scrolled, dir + L"\\preview.bmp");
    std::printf("     %d dark pixels, scrolled to %d\n", dark, scrolled);
    check(ok, "a preview of two.pdf shown, resized and unloaded");
    check(dark > 2000, "its first page drawn");
    check(scrolled > 0, "Page Down scrolls to its second page");
    ok = preview(get, dir + L"\\locked.pdf", host, &dark, &scrolled, std::wstring());
    check(ok && dark > 20, "a PDF with a password: a note instead of its pages");
    ok = preview(get, dir + L"\\garbage.pdf", host, &dark, &scrolled, std::wstring());
    check(ok && dark > 20, "a file that isn't a PDF: a note");
    DestroyWindow(host);

    std::printf(failures ? "%d FAILED\n" : "all passed\n", failures);
    OleUninitialize();
    return failures ? 1 : 0;
}
