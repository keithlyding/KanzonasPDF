# Release notes

Short, plain-language notes for each version. KanzonasPDF's update box shows the notes of every
version newer than the one you have, so you see everything that changed since your version.
The full details are in [CHANGELOG.md](CHANGELOG.md).

Every version gets a section `## <version>` (a few lines under **New** and **Fixed**), and its
Spanish translation under `## <version> (es)`. The Windows build fails without them.

## 1.6

**New**
- The Home tab starts with the three ways the mouse works: Select, Hand and CAD.
- CAD mode commands work as in AutoCAD both ways: select first and then the command, or the command first, then select and press Enter (or right-click).
- Trim asks for the cutting edges first (select them and press Enter, or just Enter to let every line cut), then cuts up to those.

**Fixed**
- CAD mode's selection takes everything at once: the drawing's lines, text and pictures and your markups on it, by click, box or lasso (the boxes only took markups before, so on a plain drawing nothing was selected). Move, Copy, Rotate, Delete and the other CAD commands work on all of it together, and one Ctrl+Z undoes it.
- Moving a text box, stamp or measurement no longer turns its words into page text, and moving the drawing's own text no longer removes a text box lying over it.
- Moving a whole sheet's text in CAD mode is much faster (45 s down to about 3 s on a heavy sheet) and uses far less memory.
- With cutting edges chosen, Trim leaves a line that crosses none of them instead of deleting it.
- Arrow keys and the right-click Delete work on the whole CAD selection; a locked comment can't be picked up through its comment card.

## 1.6 (es)

**Novedades**
- La pestaña Inicio empieza con las tres maneras de usar el mouse: Seleccionar, Mano y CAD.
- Los comandos del modo CAD funcionan como en AutoCAD de las dos maneras: seleccionar primero y luego el comando, o el comando primero, luego seleccionar y presionar Enter (o clic derecho).
- Recortar pide primero los bordes de corte (selecciónelos y presione Enter, o solo Enter para que corten todas las líneas) y luego recorta hasta ellos.

**Correcciones**
- La selección del modo CAD toma todo a la vez: las líneas, el texto y las imágenes del dibujo y sus marcas encima, con clic, recuadro o lazo (antes los recuadros solo tomaban marcas, así que en un dibujo sin marcas no se seleccionaba nada). Mover, Copiar, Girar, Eliminar y los demás comandos CAD trabajan sobre todo junto, y un solo Ctrl+Z lo deshace.
- Mover un cuadro de texto, un sello o una medida ya no convierte sus palabras en texto de la página, y mover el texto propio del dibujo ya no quita un cuadro de texto que esté encima.
- Mover todo el texto de un plano en el modo CAD es mucho más rápido (de 45 s a unos 3 s en un plano pesado) y usa mucha menos memoria.
- Con bordes de corte elegidos, Recortar deja una línea que no cruza ninguno en lugar de borrarla.
- Las teclas de flecha y Eliminar del clic derecho trabajan sobre toda la selección CAD; un comentario bloqueado no se puede tomar a través de su tarjeta.

## 1.5.1

**Fixed**
- Text added after saving showed no letters. It shows now.
- Save asks before replacing a file another program changed, and a file already open in another window isn't opened twice.
- Editing big plan sets is much quicker (each markup or change on a 200-sheet set: 3 s before, under half a second now).
- Sanitize and Apply redactions remove every script and program-launching link, and the data typed into forms.
- A second digital signature no longer breaks the first, and signed PDFs are always recognized.
- Forms: renaming fields, maximum length, dropdown values, fields on turned pages, tab order, and blank forms staying fillable after protecting them.
- Moving pages could show one page twice and put markups on the wrong page.
- Cut no longer applies pending redactions or removes letters from the lines around; Replace warns when text runs over.
- A bad settings value can no longer stop KanzonasPDF from starting.
- Printing follows each markup's "print" setting, shows its progress and can be canceled.
- Combining files keeps a PDF's copy protection; many smaller fixes.

## 1.5.1 (es)

**Correcciones**
- El texto agregado después de guardar no mostraba letras. Ahora se ve.
- Guardar pregunta antes de reemplazar un archivo que otro programa cambió, y un archivo ya abierto en otra ventana no se abre dos veces.
- Editar juegos de planos grandes es mucho más rápido (cada marca o cambio en un juego de 200 hojas: antes 3 s, ahora menos de medio segundo).
- Sanear y Aplicar censuras quitan todos los scripts y los vínculos que inician programas, y los datos escritos en los formularios.
- Una segunda firma digital ya no invalida la primera, y los PDF firmados siempre se reconocen.
- Formularios: cambiar el nombre de los campos, la longitud máxima, los valores de las listas desplegables, los campos en páginas giradas, el orden de tabulación, y los formularios en blanco siguen rellenables después de protegerlos.
- Mover páginas podía mostrar una página dos veces y poner marcas en la página equivocada.
- Cortar ya no aplica censuras pendientes ni quita letras de las líneas cercanas; Reemplazar avisa cuando el texto se sale.
- Un valor de configuración dañado ya no impide que KanzonasPDF se inicie.
- La impresión respeta la opción "imprimir" de cada marca, muestra su progreso y se puede cancelar.
- Combinar archivos conserva la protección contra copia de un PDF; muchas correcciones menores.

## 1.5

**New**
- Spanish: the whole app and its manual (File > Preferences > General > Language).
- Update now for installed copies: KanzonasPDF downloads the new version, checks it and installs it, then opens again.
- The update box lists what changed since your version, and KanzonasPDF also checks for updates while it stays open.
- Mouse mode: Standard, Hand or CAD, each with its own options (File > Preferences > Mouse).
- CAD mode selects like CAD: click, move, click for a box (left to right selects what's inside, right to left what it touches), or hold the button and draw a lasso; what it will select lights up as you go.
- A CAD tab (in CAD mode) with Move, Copy, Rotate, Scale, Mirror, Delete, Align, Array and Trim, plus the markup, measuring, snapping and clean-up tools you need next to them.
- A CAD command line at the bottom: type M, CO, RO, TR... (or any command's name) and press Enter, as in AutoCAD.
- In CAD mode, one-letter tool shortcuts can keep working (File > Preferences > Mouse). If you used the CAD-style mouse before, they still work.
- Free page movement: drag the page anywhere, even when it fits in the window.
- View > Go to: next, previous, first and last page, and Go to page (Ctrl+G). Home and End go to the first and last page.
- Faster on big CAD drawings: moving, copying, arrays and trimming are many times quicker.

**Fixed**
- Documents open while a setup updates KanzonasPDF, or while Windows shuts down, reopen at the next start when File > Preferences > Start-up and opening > "Reopen the documents..." is on, and their unsaved changes are kept as backups.
- CSV exports can't start a spreadsheet formula.
- The paragraph edit box always covers the whole paragraph.
- A straight level or vertical line selected with Edit objects rotates about its middle, has its handles on it, and can be brought forward.
- Picking another tool applies the text you were typing with Edit text.
- Ctrl+C copies a picture selected with Edit objects.
- Several smaller fixes from an outside review.

## 1.5 (es)

**Novedades**
- Español: toda la aplicación y su manual (Archivo > Preferencias > General > Idioma).
- Actualizar ahora en copias instaladas: KanzonasPDF descarga la nueva versión, la comprueba, la instala y se vuelve a abrir.
- El cuadro de actualización muestra lo que cambió desde su versión, y KanzonasPDF también busca actualizaciones mientras sigue abierto.
- Modo del mouse: Estándar, Mano o CAD, cada uno con sus propias opciones (Archivo > Preferencias > Mouse).
- El modo CAD selecciona como en CAD: clic, mover, clic para un recuadro (de izquierda a derecha selecciona lo que queda dentro, de derecha a izquierda lo que toca), o mantenga presionado el botón y dibuje un lazo; lo que seleccionará se resalta mientras lo dibuja.
- Una pestaña CAD (en el modo CAD) con Mover, Copiar, Girar, Escalar, Simetría, Eliminar, Alinear, Matriz y Recortar, además de las herramientas de marcas, medición, ajuste y limpieza que se necesitan junto a ellos.
- Una línea de comandos CAD en la parte inferior: escriba M, CO, RO, TR... (o el nombre de cualquier comando) y presione Enter, como en AutoCAD.
- En el modo CAD, los atajos de una letra de las herramientas pueden seguir funcionando (Archivo > Preferencias > Mouse). Si usaba el mouse estilo CAD antes, siguen funcionando.
- Movimiento libre de la página: arrastre la página a cualquier lugar, aunque quepa en la ventana.
- Ver > Ir a: página siguiente, anterior, primera y última, e Ir a la página (Ctrl+G). Inicio y Fin van a la primera y a la última página.
- Más rápido en dibujos CAD grandes: mover, copiar, las matrices y recortar son mucho más rápidos.

**Correcciones**
- Los documentos abiertos mientras un instalador actualiza KanzonasPDF, o mientras Windows se apaga, se vuelven a abrir en el siguiente inicio cuando Archivo > Preferencias > Inicio y apertura > "Volver a abrir los documentos..." está activado, y sus cambios sin guardar se conservan como copias de seguridad.
- Las exportaciones CSV no pueden iniciar una fórmula de hoja de cálculo.
- El cuadro de edición de párrafos siempre cubre el párrafo entero.
- Una línea recta horizontal o vertical seleccionada con Editar objetos gira sobre su centro, tiene sus controladores sobre ella y se puede traer hacia adelante.
- Al elegir otra herramienta se aplica el texto que estaba escribiendo con Editar texto.
- Ctrl+C copia una imagen seleccionada con Editar objetos.
- Varias correcciones menores de una revisión externa.
