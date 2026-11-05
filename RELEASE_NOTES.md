# Release notes

Short, plain-language notes for each version. KanzonasPDF's update box shows the notes of every
version newer than the one you have, so you see everything that changed since your version.
The full details are in [CHANGELOG.md](CHANGELOG.md).

Every version gets a section `## <version>` (a few lines under **New** and **Fixed**), and its
Spanish translation under `## <version> (es)`. The Windows build fails without them.

## 1.8.2

**New**
- A refreshed logo (Help > About): "Kanzonas" and "PDF" set in clean, matching letters, with "PDF" in red. It matches KanzonasCAD's logo letter for letter.
- The "PDF" on the icon shades from red to a deeper red, as in the logo.

## 1.8.2 (es)

**Novedades**
- Un logotipo renovado (Ayuda > Acerca de): "Kanzonas" y "PDF" con letras limpias y a juego, con "PDF" en rojo. Coincide letra por letra con el logotipo de KanzonasCAD.
- El "PDF" del icono pasa del rojo a un rojo más oscuro, como en el logotipo.

## 1.8.1

**Fixed**
- Moving a picture strip no longer makes part of the page disappear. Files made by printing a protected PDF to PDF are often built from strips of pictures, each shown through its own window; moving one used to leave the window behind, so the picture vanished. Now the window moves with it.
- Snap to page now works when you drag a picture: its edges and its center line up with the page's edges and center, with a green guide line, so a picture dropped near the middle settles exactly in the middle. Dragged markups snap the same way (before, only their top-left corner snapped).

**New**
- Every button's tool tip shows its keyboard shortcut, including keys you changed in Keyboard shortcuts. On the CAD tab the tip says what to type on the command line (Move: type M and press Enter).

## 1.8.1 (es)

**Correcciones**
- Mover una franja de imagen ya no hace desaparecer parte de la página. Los archivos creados al imprimir a PDF un PDF protegido suelen estar hechos de franjas de imagen, cada una mostrada a través de su propia ventana; al mover una, la ventana se quedaba atrás y la imagen desaparecía. Ahora la ventana se mueve con ella.
- Ajustar a la página ahora funciona al arrastrar una imagen: sus bordes y su centro se alinean con los bordes y el centro de la página, con una línea guía verde, así que una imagen soltada cerca del centro queda exactamente en el centro. Las marcas arrastradas se ajustan de la misma forma (antes solo se ajustaba su esquina superior izquierda).

**Novedades**
- La información sobre herramientas de cada botón muestra su método abreviado de teclado, incluidas las teclas que haya cambiado en Métodos abreviados de teclado. En la pestaña CAD indica qué escribir en la línea de comandos (Mover: escriba M y presione Enter).

## 1.8

**New**
- A new Print tab with print production tools for plotters and print shops:
  - Set page boxes: the trim box (finished size), bleed box and art box of your pages. Show page boxes outlines them on screen.
  - Fix hairlines: lines too thin to print well (including width 0) are drawn at a width you choose.
  - Check for printing: a quick report of common printing problems (fonts not embedded, low-resolution or RGB pictures, mixed sheet sizes, no trim or bleed, hairlines), with a click to go to each page.
  - Crop marks in the Print window, at the trim box, on the paper only.
- A new icon: "PDF" on a tag across the bottom, to match KanzonasCAD.

## 1.8 (es)

**Novedades**
- Una nueva pestaña Imprimir con herramientas de producción de impresión para trazadores e imprentas:
  - Establecer cuadros de página: el cuadro de recorte final (tamaño terminado), el de sangrado y el de arte de sus páginas. Mostrar cuadros de página los delinea en pantalla.
  - Corregir líneas finas: las líneas demasiado finas para imprimirse bien (incluido el grosor 0) se dibujan con el grosor que elija.
  - Revisar para imprimir: un informe rápido de problemas de impresión comunes (fuentes no incrustadas, imágenes de baja resolución o RGB, tamaños de hoja mezclados, sin recorte final ni sangrado, líneas finas), con un clic para ir a cada página.
  - Marcas de corte en la ventana Imprimir, en el cuadro de recorte final, solo en el papel.
- Un nuevo icono: «PDF» en una etiqueta en la parte inferior, a juego con KanzonasCAD.

## 1.7.3

**Fixed**
- Links can be opened again in every mouse mode: hold Ctrl and click a link, whatever tool you're using (Select, Edit objects in CAD mode, the drawing and measuring tools...). Holding Ctrl over a link shows a hand and where it goes. With the Hand tool a plain click still opens it.

## 1.7.3 (es)

**Correcciones**
- Los vínculos se pueden abrir de nuevo en todos los modos del mouse: mantenga presionada Ctrl y haga clic en un vínculo, sea cual sea la herramienta que use (Seleccionar, Editar objetos en el modo CAD, las herramientas de dibujo y medición...). Al mantener Ctrl sobre un vínculo se ve una mano y adónde lleva. Con la herramienta Mano, un clic normal lo sigue abriendo.

## 1.7.2

**New**
- In CAD mode, double-click on text to edit it: the page's own text opens in Edit text, and a markup's text (a text box, a note) opens in its editor.
- In CAD mode, selected items can be resized: one markup by its own handles, and several items (markups together with lines and shapes of the drawing) by one box with handles around them all.

**Fixed**
- Switching the mouse (for example from Select to Hand) no longer moves the page to the far left when you're zoomed out.
- A PDF protected against changes no longer shows a message every time it opens. The message now appears when you try to change it, and Edit text says so before you start typing.

## 1.7.2 (es)

**Novedades**
- En el modo CAD, haga doble clic en un texto para editarlo: el texto propio de la página se abre en Editar texto, y el texto de una marca (un cuadro de texto, una nota) en su editor.
- En el modo CAD se puede cambiar el tamaño de lo seleccionado: una marca con sus propios controladores, y varios elementos (marcas junto con líneas y formas del dibujo) con un solo recuadro con controladores alrededor de todos.

**Correcciones**
- Cambiar el mouse (por ejemplo de Seleccionar a Mano) ya no lleva la página al extremo izquierdo cuando la vista está alejada.
- Un PDF protegido contra cambios ya no muestra un mensaje cada vez que se abre. El mensaje aparece ahora al intentar cambiarlo, y Editar texto lo indica antes de empezar a escribir.

## 1.7.1

**New**
- Trim works on arcs, curves, arrows, circles and ellipses. What's left of an arc or a curve is still an arc or a curve, an arrow keeps its head on the part with the tip, and a circle cut in two places leaves an arc. Curves that are part of the drawing stay smooth, and lines some CAD programs draw as thin filled bars are trimmed too.
- In CAD mode, the pointer shows what a click will take: the cross gets a small pick box and the item turns lighter while the pointer is over it.
- In CAD mode a selection box can start in the gray area around the page, and a sheet covered by a background or a scan no longer gets in the way of starting one.
- The CAD tab has Edit text (with Add text under its arrow) in its Edit group (formerly Clean up).

**Fixed**
- Align and Distribute work on a mix of items: markups together with lines, shapes, pictures and text of the page itself. Before, the buttons stayed grayed out.
- The app now includes one copy of the OpenCV picture library (used by OCR and by export to Word) instead of two copies that could conflict.

## 1.7.1 (es)

**Novedades**
- Recortar funciona en arcos, curvas, flechas, círculos y elipses. Lo que queda de un arco o una curva sigue siendo un arco o una curva, una flecha conserva la punta en la parte de su extremo, y un círculo cortado en dos lugares deja un arco. Las curvas propias del dibujo siguen siendo suaves, y también se recortan las líneas que algunos programas CAD dibujan como barras finas rellenas.
- En el modo CAD, el puntero muestra lo que tomará un clic: la cruz muestra un pequeño cuadro de selección y el elemento se ve más claro mientras el puntero está encima.
- En el modo CAD un recuadro de selección puede empezar en el área gris alrededor de la página, y una hoja cubierta por un fondo o un escaneo ya no impide empezarlo.
- La pestaña CAD tiene Editar texto (con Agregar texto bajo su flecha) en su grupo Editar (antes Limpiar).

**Correcciones**
- Alinear y Distribuir funcionan con una mezcla de elementos: marcas junto con líneas, formas, imágenes y texto de la propia página. Antes, los botones se quedaban desactivados.
- La aplicación ahora incluye una sola copia de la biblioteca de imágenes OpenCV (que usan el OCR y la exportación a Word) en lugar de dos copias que podían entrar en conflicto.

## 1.7

**New**
- KanzonasPDF for Linux: download KanzonasPDF-x86_64.AppImage from the release page, make it executable and run it (see the README or Help > User manual > KanzonasPDF on Linux). It runs on Ubuntu 22.04, Debian 12, Fedora 36 and later.
- On Linux, Preferences can add KanzonasPDF to the applications menu and make it the app that opens PDFs, and Update now replaces the AppImage with the new version.

**Fixed**
- The ribbon no longer shifts slightly when you change the theme (Linux).

## 1.7 (es)

**Novedades**
- KanzonasPDF para Linux: descargue KanzonasPDF-x86_64.AppImage de la página de la versión, hágalo ejecutable y ábralo (vea el README o Ayuda > Manual del usuario > KanzonasPDF en Linux). Funciona en Ubuntu 22.04, Debian 12, Fedora 36 y posteriores.
- En Linux, Preferencias puede agregar KanzonasPDF al menú de aplicaciones y hacer que abra los PDF, y Actualizar ahora reemplaza la AppImage por la nueva versión.

**Correcciones**
- La cinta ya no se desplaza un poco al cambiar el tema (Linux).

## 1.6.3

**New**
- In CAD mode, shapes are drawn like in AutoCAD: click where it starts, move, and click where it ends (no need to hold the button). Dragging still works.
- New tools: Circle (click the center, then the edge, or type the radius), Arc (three points), Curve, and Mask (a white box that hides what's under it on screen and in print; use Redact to really remove content).
- Bend a line or arrow: select it and drag the diamond in its middle to make it a smooth curve.
- Trim now works on rectangles, polygons and clouds: click a side to take it away, corner to corner. A trimmed cloud stays a cloud.
- The CAD tab groups similar tools under one button with a down arrow (Rectangle, Cloud, Polygon, Mask; Circle and Arc; Line, Polyline, Curve and Pen; all measurements; arrange and align), and switching to CAD mode brings the CAD tab to the front.

**Fixed**
- In CAD mode, selected items are easy to see: they're drawn dashed with small grips on their ends and corners, even when the item itself is blue.
- The click, move, click selection box starts reliably: a click with the mouse moving slightly no longer turns into a lasso, and clicking the first corner again keeps the box. The first corner shows at once.
- In CAD mode a drawing tool always draws, even when you start on a markup (it snaps to its end), as in AutoCAD.
- Sanitize and Apply redactions now also remove scripts hidden in multimedia actions, javascript: links and XFA forms; Search & redact also replaces the text in tagged-PDF alternate text, link notes and page labels.
- Compress keeps the document's password protection; Compare asks for a protected file's password; Security properties asks before removing protection.
- Fixes and speed-ups from testing: drawing a box with level corners, a typed radius with a decimal comma, the Mask's outline after restyling, a keyboard shortcut you had set no longer taken by the new Circle key, and big selections, curves and long clouds stay quick.

## 1.6.3 (es)

**Novedades**
- En el modo CAD, las formas se dibujan como en AutoCAD: haga clic donde empieza, mueva el mouse y haga clic donde termina (sin mantener presionado el botón). Arrastrar sigue funcionando.
- Herramientas nuevas: Círculo (clic en el centro y luego en el borde, o escriba el radio), Arco (tres puntos), Curva y Máscara (un cuadro blanco que oculta lo que hay debajo en pantalla y al imprimir; use Censurar para eliminar contenido de verdad).
- Curvar una línea o flecha: selecciónela y arrastre el rombo de su centro para convertirla en una curva suave.
- Recortar ahora funciona en rectángulos, polígonos y nubes: haga clic en un lado para quitarlo, de esquina a esquina. Una nube recortada sigue siendo una nube.
- La pestaña CAD agrupa las herramientas parecidas en un botón con una flecha (Rectángulo, Nube, Polígono, Máscara; Círculo y Arco; Línea, Polilínea, Curva y Lápiz; todas las medidas; organizar y alinear), y al pasar al modo CAD la pestaña CAD pasa al frente.

**Correcciones**
- En el modo CAD lo seleccionado se ve claramente: se dibuja con línea discontinua y pequeños pinzamientos en sus extremos y esquinas, aunque el elemento mismo sea azul.
- El recuadro de selección de clic, mover, clic empieza sin fallar: un clic con el mouse moviéndose un poco ya no se convierte en lazo, y volver a hacer clic en la primera esquina conserva el recuadro. La primera esquina se muestra de inmediato.
- En el modo CAD una herramienta de dibujo siempre dibuja, aunque empiece sobre una marca (se ajusta a su extremo), como en AutoCAD.
- Sanear y Aplicar censuras ahora también quitan los scripts ocultos en acciones multimedia, vínculos javascript: y formularios XFA; Buscar y censurar también reemplaza el texto en el texto alternativo de los PDF etiquetados, las notas de vínculos y las etiquetas de página.
- Comprimir conserva la protección con contraseña del documento; Comparar pide la contraseña de un archivo protegido; Propiedades de seguridad pregunta antes de quitar la protección.
- Correcciones y mejoras de velocidad de las pruebas: dibujar un cuadro con esquinas al mismo nivel, un radio escrito con coma decimal, el contorno de la Máscara después de cambiar su estilo, un atajo de teclado que usted había asignado ya no se lo quita la nueva tecla de Círculo, y las selecciones grandes, las curvas y las nubes largas siguen siendo rápidas.

## 1.6.2

**Fixed**
- Undo and redo are much quicker on big files, and use far less memory: each step keeps only what the edit changed instead of a copy of the whole document. On an 80 MB drawing set an edit takes about a tenth of the time, and all 30 undo steps fit even on very large files.
- Adding, moving or deleting a markup on a heavy drawing or a big scan no longer redraws the whole sheet: the page updates in a few hundredths of a second instead of up to several seconds.
- Zooming with the mouse wheel follows at once on heavy drawings; the page is drawn sharp as soon as the wheel stops, the middle of the window first. Big scans decode their picture once, so panning and zooming them is several times faster.
- Heavy CAD sheets: the first click, Erase content and reading a sheet for CAD mode are two to five times faster; Apply redactions and Sanitize on sheets without text take a couple of seconds instead of half a minute, and still remove hidden text exactly as before.
- Thumbnails of heavy sheets appear almost at once.
- The split view now follows night mode, thin lines, Show markups, field shading and the layers you show or hide.
- Filling in a form field that appears on several pages updates every page that shows it.
- At 125%, 150% and 175% Windows display scaling, big pages no longer leave thin lines of old pixels at tile and page edges.
- Delete comments works again on documents with markups.
- KanzonasPDF no longer closes suddenly when you search, select or copy text on certain pages (a picture or drawing marked with alternate text inside other alternate text, which crashed the PDF engine).

## 1.6.2 (es)

**Correcciones**
- Deshacer y rehacer son mucho más rápidos en archivos grandes y usan mucha menos memoria: cada paso guarda solo lo que cambió la edición en lugar de una copia de todo el documento. En un juego de planos de 80 MB una edición tarda una décima parte, y los 30 pasos de deshacer caben incluso en archivos muy grandes.
- Agregar, mover o eliminar una marca en un plano pesado o un escaneo grande ya no vuelve a dibujar toda la hoja: la página se actualiza en unas centésimas de segundo en lugar de hasta varios segundos.
- El zoom con la rueda del mouse sigue al instante en planos pesados; la página se dibuja nítida en cuanto la rueda se detiene, primero el centro de la ventana. Los escaneos grandes decodifican su imagen una sola vez, así que desplazarlos y hacer zoom es varias veces más rápido.
- Planos CAD pesados: el primer clic, Borrar contenido y la lectura de una hoja para el modo CAD son de dos a cinco veces más rápidos; Aplicar redacciones y Sanear en hojas sin texto tardan un par de segundos en lugar de medio minuto, y siguen quitando el texto oculto exactamente igual que antes.
- Las miniaturas de las hojas pesadas aparecen casi al instante.
- La vista dividida ahora sigue al modo nocturno, las líneas finas, Mostrar marcas, el sombreado de campos y las capas que muestra u oculta.
- Llenar un campo de formulario que aparece en varias páginas actualiza todas las páginas que lo muestran.
- Con la escala de pantalla de Windows al 125%, 150% y 175%, las páginas grandes ya no dejan líneas finas de píxeles viejos en los bordes de los mosaicos y de la página.
- Eliminar comentarios vuelve a funcionar en documentos con marcas.
- KanzonasPDF ya no se cierra de repente al buscar, seleccionar o copiar texto en ciertas páginas (una imagen o un dibujo marcado con texto alternativo dentro de otro texto alternativo, que hacía fallar el motor PDF).

## 1.6.1

**Fixed**
- Editing pages with many markups is much faster: with 1,000 markups on a page, adding them takes under half a second instead of over three, moving them half a second instead of thirteen, and deleting them a third of a second instead of four.
- Moving a markup no longer redraws it: it lands exactly where you put it, and a box made by another program no longer grows slightly each time it is moved.
- Long documents: inserting, deleting and turning pages no longer freeze the window (inserting 500 pages into a 2,000-page set took about 9 seconds, now a tenth of a second); thumbnails are no longer redrawn when you switch tabs; autosave, big forms and the markups list are much quicker.
- Every mouse move stays instant: selecting text, hovering over pages with many markups, Edit objects and Edit text, and the preview of CAD commands on big selections.
- Heavy drawings: CAD edits and copies are two to three times faster, undo takes far less memory, snapping is ready sooner, and night mode draws ten times faster.
- Restyling or editing a comment's markup no longer deletes the replies to it, and locking or hiding a measurement keeps its label.
- A value being typed in a form field is no longer lost when a page is moved, turned or deleted.
- Snapping follows Crop pages and the layers you show or hide.
- The selection highlight and repainting no longer lag when thousands of markups are selected or under a CAD selection box.

## 1.6.1 (es)

**Correcciones**
- Editar páginas con muchas marcas es mucho más rápido: con 1,000 marcas en una página, agregarlas tarda menos de medio segundo en lugar de más de tres, moverlas medio segundo en lugar de trece, y eliminarlas un tercio de segundo en lugar de cuatro.
- Mover una marca ya no la vuelve a dibujar: queda exactamente donde la pone, y un recuadro hecho por otro programa ya no crece un poco cada vez que se mueve.
- Documentos largos: insertar, eliminar y girar páginas ya no congela la ventana (insertar 500 páginas en un juego de 2,000 tardaba unos 9 segundos, ahora una décima de segundo); las miniaturas ya no se vuelven a dibujar al cambiar de pestaña; el autoguardado, los formularios grandes y la lista de marcas son mucho más rápidos.
- Cada movimiento del mouse sigue siendo instantáneo: seleccionar texto, pasar sobre páginas con muchas marcas, Editar objetos y Editar texto, y la vista previa de los comandos CAD con selecciones grandes.
- Planos pesados: las ediciones y copias CAD son dos a tres veces más rápidas, deshacer usa mucha menos memoria, el ajuste a objetos está listo antes y el modo nocturno dibuja diez veces más rápido.
- Cambiar el estilo o editar la marca de un comentario ya no elimina sus respuestas, y bloquear u ocultar una medida conserva su etiqueta.
- Un valor que se está escribiendo en un campo de formulario ya no se pierde al mover, girar o eliminar una página.
- El ajuste a objetos sigue a Recortar páginas y a las capas que muestra u oculta.
- El resaltado de la selección y el redibujado ya no se retrasan cuando hay miles de marcas seleccionadas o dentro de un recuadro de selección CAD.

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
