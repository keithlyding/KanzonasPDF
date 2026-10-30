# Release notes

Short, plain-language notes for each version. KanzonasPDF's update box shows the notes of every
version newer than the one you have, so you see everything that changed since your version.
The full details are in [CHANGELOG.md](CHANGELOG.md).

Every version gets a section `## <version>` (a few lines under **New** and **Fixed**), and its
Spanish translation under `## <version> (es)`. The Windows build fails without them.

## 1.5

**New**
- Spanish: the whole app and its manual (File > Preferences > General > Language).
- Update now for installed copies: KanzonasPDF downloads the new version, checks it and installs it, then opens again.
- The update box lists what changed since your version, and KanzonasPDF also checks for updates while it stays open.
- Mouse mode: Standard, Hand or CAD, each with its own options (File > Preferences > Mouse).
- CAD mode selects like CAD: click, move, click for a box (left to right selects what's inside, right to left what it touches), or hold the button and draw a lasso; what it will select lights up as you go.
- A CAD tab (in CAD mode) with Move, Copy, Rotate, Scale, Mirror, Delete, Align, Array and Trim.
- A CAD command line at the bottom: type M, CO, RO, TR... (or any command's name) and press Enter, as in AutoCAD.
- Free page movement: drag the page anywhere, even when it fits in the window.
- Faster on big CAD drawings: moving, copying, arrays and trimming are many times quicker.

**Fixed**
- Documents open while a setup updates KanzonasPDF, or while Windows shuts down, reopen at the next start when File > Preferences > Start-up and opening > "Reopen the documents..." is on, and their unsaved changes are kept as backups.
- CSV exports can't start a spreadsheet formula.
- The paragraph edit box always covers the whole paragraph.
- Several smaller fixes from an outside review.

## 1.5 (es)

**Novedades**
- Español: toda la aplicación y su manual (Archivo > Preferencias > General > Idioma).
- Actualizar ahora en copias instaladas: KanzonasPDF descarga la nueva versión, la comprueba, la instala y se vuelve a abrir.
- El cuadro de actualización muestra lo que cambió desde su versión, y KanzonasPDF también busca actualizaciones mientras sigue abierto.
- Modo del mouse: Estándar, Mano o CAD, cada uno con sus propias opciones (Archivo > Preferencias > Mouse).
- El modo CAD selecciona como en CAD: clic, mover, clic para un recuadro (de izquierda a derecha selecciona lo que queda dentro, de derecha a izquierda lo que toca), o mantenga presionado el botón y dibuje un lazo; lo que seleccionará se resalta mientras lo dibuja.
- Una pestaña CAD (en el modo CAD) con Mover, Copiar, Girar, Escalar, Simetría, Eliminar, Alinear, Matriz y Recortar.
- Una línea de comandos CAD en la parte inferior: escriba M, CO, RO, TR... (o el nombre de cualquier comando) y presione Enter, como en AutoCAD.
- Movimiento libre de la página: arrastre la página a cualquier lugar, aunque quepa en la ventana.
- Más rápido en dibujos CAD grandes: mover, copiar, las matrices y recortar son mucho más rápidos.

**Correcciones**
- Los documentos abiertos mientras un instalador actualiza KanzonasPDF, o mientras Windows se apaga, se vuelven a abrir en el siguiente inicio cuando Archivo > Preferencias > Inicio y apertura > "Volver a abrir los documentos..." está activado, y sus cambios sin guardar se conservan como copias de seguridad.
- Las exportaciones CSV no pueden iniciar una fórmula de hoja de cálculo.
- El cuadro de edición de párrafos siempre cubre el párrafo entero.
- Varias correcciones menores de una revisión externa.
