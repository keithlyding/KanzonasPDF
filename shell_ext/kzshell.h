// KanzonasPDF's Windows Explorer handlers: their class IDs. The installer
// (installer/KanzonasPDF.iss) registers the same ones; tests/test_shell_ext.py checks they match.
#pragma once
#include <guiddef.h>

// {8BBD1C01-BC86-4432-9CA0-D3F973DBF51C}: a PDF's first page as its picture in Explorer
static const CLSID CLSID_KzThumbnail =
    {0x8bbd1c01, 0xbc86, 0x4432, {0x9c, 0xa0, 0xd3, 0xf9, 0x73, 0xdb, 0xf5, 0x1c}};
// {6F5FD26D-63FE-481F-8E9D-F28ADC1924C3}: its pages in Explorer's Preview pane
static const CLSID CLSID_KzPreview =
    {0x6f5fd26d, 0x63fe, 0x481f, {0x8e, 0x9d, 0xf2, 0x8a, 0xdc, 0x19, 0x24, 0xc3}};
