# Release notes

Short, plain-language notes for each version. KanzonasPDF's update box shows the notes of every
version newer than the one you have, so you see everything that changed since your version.
The full details are in [CHANGELOG.md](CHANGELOG.md).

Every version gets a section `## <version>` (a few lines under **New** and **Fixed**), and its
Spanish translation under `## <version> (es)`. The Windows build fails without them. An Italian
translation under `## <version> (it)` is shown to Italian users (since 1.13); without one they
see the English.

## 1.16.3

**New**
- Wall area from a length: give a Length or Polylength measurement a Height in Properties, and it shows the wall area too (length × height), for drywall, paint, insulation or masonry. The Measurement summary and the Excel takeoff list it as a Wall area.
- Crop pages: the box snaps to the page's corners and edges with Snap to page on (and to the grid and objects, as shapes do).
- Print: the paper size is on the Print window (the printer's own sizes; Page setup is for the margins), and each document remembers what it was last printed with: printer, paper, copies, pages and the other settings.
- Drops and rises on runs: right-click near a point of a Polylength measurement > Add drop or rise..., for conduit, wire and pipe runs. Its total includes the vertical runs the plan doesn't show; each drop is named at its point, and the Measurement summary, the Excel takeoff and legends count the total.
- A quantity per count, and waste: for a Count group, Properties > Quantities and waste... sets what each counted item stands for (each fixture = 2 boxes + 1 whip, with their units) and a waste percent; lengths, areas and volumes have their own Waste / extra. The Measurement summary and the Excel takeoff show the counts, the resulting quantities and the quantities with waste.
- Slope for roof areas: type a pitch (6:12, or 30°) in an Area measurement's Slope in Properties, and it shows, sums and exports the sloped area, for roofing and framing.

**Fixed**
- Callouts made in another program (Bluebeam, Acrobat): changing their text size or resizing their box sent their arrow to the corner of the page; they're now read as callouts and their arrows stay where they point.
- The page's text moved together with a markup by the arrow keys stays selected when it reaches other text (it was unselected after the first press).
- Mac: when GitHub has no Mac free to build a version, it goes out without the Mac download; KanzonasPDF on a Mac tells you only about versions that have one.

## 1.16.3 (es)

**Novedades**
- Área de muro desde una longitud: dé a una medición de Longitud o Longitud de polilínea una Altura en Propiedades, y muestra también el área del muro (longitud × altura), para paneles de yeso, pintura, aislamiento o mampostería. El Resumen de mediciones y la medición en Excel la muestran como Área de muro.
- Recortar páginas: el cuadro se ajusta a las esquinas y bordes de la página con Ajustar a la página activado (y a la cuadrícula y los objetos, como las formas).
- Imprimir: el tamaño del papel está en la ventana Imprimir (los tamaños de la impresora; Configurar página es para los márgenes), y cada documento recuerda con qué se imprimió la última vez: impresora, papel, copias, páginas y los demás ajustes.
- Bajadas y subidas en recorridos: clic derecho cerca de un punto de una medición de Longitud de polilínea > Agregar bajada o subida..., para recorridos de tubo, cable y tubería. Su total incluye los tramos verticales que el plano no muestra; cada bajada se nombra en su punto, y el Resumen de mediciones, la medición en Excel y las leyendas cuentan el total.
- Una cantidad por conteo, y desperdicio: para un grupo de Conteo, Propiedades > Cantidades y desperdicio... define lo que representa cada elemento contado (cada aparato = 2 cajas + 1 latiguillo, con sus unidades) y un porcentaje de desperdicio; las longitudes, áreas y volúmenes tienen su propio Desperdicio / extra. El Resumen de mediciones y la medición en Excel muestran los conteos, las cantidades resultantes y las cantidades con desperdicio.
- Pendiente para áreas de cubierta: escriba una pendiente (6:12, o 30°) en la Pendiente de una medición de Área en Propiedades, y muestra, suma y exporta el área inclinada, para cubiertas y estructura.

**Correcciones**
- Llamadas hechas en otro programa (Bluebeam, Acrobat): cambiar el tamaño del texto o del cuadro mandaba su flecha a la esquina de la página; ahora se leen como llamadas y sus flechas se quedan donde apuntan.
- El texto de la página movido junto con una marca con las flechas sigue seleccionado al llegar a otro texto (se deseleccionaba tras la primera pulsación).
- Mac: cuando GitHub no tiene un Mac libre para crear una versión, esta sale sin la descarga para Mac; KanzonasPDF en un Mac solo avisa de las versiones que la tienen.

## 1.16.3 (it)

**Novità**
- Area della parete da una lunghezza: dai a una misura di Lunghezza o Lunghezza polilinea un'Altezza in Proprietà, e mostra anche l'area della parete (lunghezza × altezza), per cartongesso, pittura, isolamento o muratura. Il Riepilogo misure e il computo in Excel la elencano come Area parete.
- Ritaglia pagine: il riquadro si aggancia agli angoli e ai bordi della pagina con Aggancia alla pagina attivo (e alla griglia e agli oggetti, come le forme).
- Stampa: il formato della carta è nella finestra Stampa (i formati della stampante; Imposta pagina è per i margini), e ogni documento ricorda con cosa è stato stampato l'ultima volta: stampante, carta, copie, pagine e le altre impostazioni.
- Discese e risalite sui percorsi: clic destro vicino a un punto di una misura di Lunghezza polilinea > Aggiungi discesa o risalita..., per percorsi di tubi, cavi e tubazioni. Il totale comprende i tratti verticali che la pianta non mostra; ogni discesa è indicata al suo punto, e il Riepilogo misure, il computo in Excel e le legende contano il totale.
- Una quantità per conteggio, e sfrido: per un gruppo di Conteggio, Proprietà > Quantità e sfrido... imposta cosa rappresenta ogni elemento contato (ogni apparecchio = 2 scatole + 1 cavo, con le loro unità) e una percentuale di sfrido; lunghezze, aree e volumi hanno il proprio Sfrido / extra. Il Riepilogo misure e il computo in Excel mostrano i conteggi, le quantità risultanti e le quantità con lo sfrido.
- Pendenza per le aree di copertura: digita una pendenza (6:12, o 30°) nella Pendenza di una misura di Area in Proprietà, e mostra, somma ed esporta l'area inclinata, per coperture e carpenteria.

**Correzioni**
- Richiami fatti in un altro programma (Bluebeam, Acrobat): cambiare la dimensione del testo o del riquadro mandava la freccia nell'angolo della pagina; ora sono letti come richiami e le frecce restano dove puntano.
- Il testo della pagina spostato insieme a un'annotazione con i tasti freccia resta selezionato quando arriva su altro testo (veniva deselezionato dopo la prima pressione).
- Mac: quando GitHub non ha un Mac libero per creare una versione, questa esce senza il download per Mac; KanzonasPDF su un Mac avvisa solo delle versioni che lo hanno.

## 1.16.2

**New**
- Measurement summary > Export Excel...: the whole takeoff as an Excel workbook, grouped by sheet, by space and by kind or Count group, with quantities, units and subtotals, and every measurement on its own row (the start of a bill of quantities). Export CSV... stays.

**Fixed**
- With hundreds of markups selected, the page draws their outlines four times faster.

## 1.16.2 (es)

**Novedades**
- Resumen de mediciones > Exportar Excel...: toda la medición como un libro de Excel, agrupada por plano, por espacio y por tipo o grupo de Recuento, con cantidades, unidades y subtotales, y cada medición en su propia fila (el comienzo de un presupuesto de cantidades). Exportar CSV... se mantiene.

**Correcciones**
- Con cientos de marcas seleccionadas, la página dibuja sus contornos cuatro veces más rápido.

## 1.16.2 (it)

**Novità**
- Riepilogo misure > Esporta Excel...: tutto il computo come cartella di lavoro Excel, raggruppato per tavola, per spazio e per tipo o gruppo di Conteggio, con quantità, unità e subtotali, e ogni misura su una riga (l'inizio di un computo metrico). Esporta CSV... resta.

**Correzioni**
- Con centinaia di annotazioni selezionate, la pagina disegna i loro contorni quattro volte più in fretta.

## 1.16.1

**New**
- Cut-outs: take openings out of an Area or Volume measurement (a stair shaft from a floor, windows and doors from a wall, a column from a slab) with Measure > Cut-out. The measurement shows its net area or volume, and the Measurement summary and legends total the net values.

**Fixed**
- Text running past the edge of a page (a label on a page cropped close) kept the letters beyond the edge when edited or restyled; they were deleted.
- Underline and strikethrough on text starting with a space (a contents row's dot leader) now show as on in Properties.

## 1.16.1 (es)

**Novedades**
- Recortes: quite aberturas de una medición de Área o Volumen (el hueco de una escalera de un piso, ventanas y puertas de un muro, una columna de una losa) con Medir > Recorte. La medición muestra su área o volumen neto, y el Resumen de mediciones y las leyendas suman los valores netos.

**Correcciones**
- El texto que pasa del borde de una página (una etiqueta en una página recortada muy justa) conserva las letras de más allá del borde al editarlo o cambiar su estilo; se borraban.
- El subrayado y el tachado en texto que empieza con un espacio (la línea de puntos de un índice) ahora aparecen activados en Propiedades.

## 1.16.1 (it)

**Novità**
- Ritagli: togli aperture da una misura di Area o Volume (il vano di una scala da un solaio, finestre e porte da una parete, un pilastro da una soletta) con Misure > Ritaglio. La misura mostra l'area o il volume netto, e il Riepilogo misure e le legende sommano i valori netti.

**Correzioni**
- Il testo che va oltre il bordo di una pagina (un'etichetta su una pagina ritagliata stretta) mantiene le lettere oltre il bordo quando lo modifichi o ne cambi lo stile; venivano cancellate.
- Sottolineatura e barrato su testo che inizia con uno spazio (i puntini di un indice) ora risultano attivi in Proprietà.

## 1.16

**New**
- Markup or page content: Properties shows which one you're changing or about to add, a markup on top of the page or the page's own content, and every tool's tooltip says it too.
- The page's own text in Properties: select it with Edit objects and change its font, size, bold, italic, underline, strikethrough, color and background there. While editing text, Properties has all of them too.
- Text background: highlight words in the page itself, as a highlighter pen on paper, as against the Highlight markup on top. It moves and rewraps with its words.

**Fixed**
- Text moved or recolored with Edit objects kept its underline and strikethrough (they were lost, and their lines stayed where the text had been).
- An underline on diagonal text (a watermark) was drawn as a large square over the word; diagonal text now gets no underline.
- Text stamped twice in the same place (a watermark): moving or recoloring one copy no longer takes the other away.

## 1.16 (es)

**Novedades**
- Marca o contenido de la página: Propiedades muestra cuál está cambiando o va a agregar, una marca encima de la página o el contenido propio de la página, y la descripción de cada herramienta también lo dice.
- El texto propio de la página en Propiedades: selecciónelo con Editar objetos y cambie allí su fuente, tamaño, negrita, cursiva, subrayado, tachado, color y fondo. Al editar texto, Propiedades también los tiene todos.
- Fondo del texto: resalte palabras en la propia página, como un marcador sobre papel, a diferencia de la marca de Resaltar que queda encima. Se mueve y se reajusta con sus palabras.

**Correcciones**
- El texto movido o con otro color en Editar objetos conserva su subrayado y su tachado (se perdían, y sus líneas quedaban donde había estado el texto).
- Un subrayado en texto en diagonal (una marca de agua) se dibujaba como un cuadrado grande sobre la palabra; el texto en diagonal ya no lleva subrayado.
- Texto estampado dos veces en el mismo lugar (una marca de agua): mover o cambiar el color de una copia ya no quita la otra.

## 1.16 (it)

**Novità**
- Annotazione o contenuto della pagina: Proprietà mostra quale stai cambiando o stai per aggiungere, un'annotazione sopra la pagina o il contenuto della pagina stessa, e lo dice anche la descrizione di ogni strumento.
- Il testo della pagina in Proprietà: selezionalo con Modifica oggetti e cambia lì il font, la dimensione, il grassetto, il corsivo, la sottolineatura, il barrato, il colore e lo sfondo. Mentre modifichi il testo, Proprietà li ha tutti.
- Sfondo del testo: evidenzia parole nella pagina stessa, come un evidenziatore sulla carta, a differenza dell'annotazione Evidenzia che sta sopra. Si sposta e va a capo con le sue parole.

**Correzioni**
- Il testo spostato o ricolorato con Modifica oggetti mantiene sottolineatura e barrato (si perdevano, e le loro linee restavano dov'era il testo).
- Una sottolineatura su testo in diagonale (una filigrana) veniva disegnata come un grande quadrato sulla parola; il testo in diagonale ora non ha sottolineatura.
- Testo timbrato due volte nello stesso punto (una filigrana): spostare o ricolorare una copia non toglie più l'altra.

## 1.15.21

**New**
- Lines you draw (Line, Arrow, Polyline, Arc, Curve): in Properties, an arrowhead at the start and at the end, each of its own kind, so a line can point both ways; a middle arrow; and a line style: solid, dashed, dotted or dash-dot.
- The drawing's own lines (Edit objects, CAD mode): Line color, Fill color, Line style and arrowheads at the start, end and middle, in Properties next to Line width. The arrowheads become part of the line and move with it.

**Fixed**
- Line width for the drawing's own lines: the arrows and a typed number now change it (it went back to the old width).
- Rotate by: the number now shows how far the selection has turned, so the arrows step it 5° at a time, instead of going back to 0 after each turn.

## 1.15.21 (es)

**Novedades**
- Las líneas que dibuja (Línea, Flecha, Polilínea, Arco, Curva): en Propiedades, una punta de flecha al inicio y otra al final, cada una de su propio tipo, para que una línea pueda apuntar en ambos sentidos; una flecha central; y un estilo de línea: continua, discontinua, punteada o raya y punto.
- Las líneas propias del dibujo (Editar objetos, modo CAD): Color de línea, Color de relleno, Estilo de línea y puntas de flecha al inicio, al final y en el centro, en Propiedades junto a Grosor de línea. Las puntas de flecha pasan a formar parte de la línea y se mueven con ella.

**Correcciones**
- Grosor de línea en las líneas propias del dibujo: las flechas y un número escrito ahora lo cambian (volvía al grosor anterior).
- Girar: el número ahora muestra cuánto ha girado la selección, así que las flechas lo cambian de 5° en 5°, en vez de volver a 0 tras cada giro.

## 1.15.21 (it)

**Novità**
- Le linee che disegni (Linea, Freccia, Polilinea, Arco, Curva): nelle Proprietà, una punta di freccia all'inizio e una alla fine, ciascuna del proprio tipo, così una linea può puntare in entrambi i sensi; una freccia centrale; e uno stile linea: continua, tratteggiata, punteggiata o tratto-punto.
- Le linee del disegno stesso (Modifica oggetti, modalità CAD): Colore linea, Colore riempimento, Stile linea e punte di freccia all'inizio, alla fine e al centro, nelle Proprietà accanto a Spessore linea. Le punte di freccia diventano parte della linea e si spostano con essa.

**Correzioni**
- Spessore linea per le linee del disegno stesso: le frecce e un numero digitato ora lo cambiano (tornava allo spessore precedente).
- Ruota di: il numero ora mostra di quanto è ruotata la selezione, così le frecce lo cambiano di 5° alla volta, invece di tornare a 0 dopo ogni rotazione.

## 1.15.20

**Fixed**
- Text added and saved, then another line in the same font added later: recoloring, moving or editing that line could make it disappear. It now keeps its letters.

## 1.15.20 (es)

**Correcciones**
- Texto añadido y guardado, y luego otra línea en la misma fuente añadida más tarde: cambiar el color, mover o editar esa línea podía hacerla desaparecer. Ahora conserva sus letras.

## 1.15.20 (it)

**Correzioni**
- Testo aggiunto e salvato, poi un'altra riga nello stesso carattere aggiunta in seguito: cambiare il colore, spostare o modificare quella riga poteva farla sparire. Ora mantiene le sue lettere.
## 1.15.19

**New**
- View > Show line weights: turn it off to draw every line thin on screen, as CAD programs do with line weights hidden. Printing, export and the file keep the real line widths. Also in Preferences and under the arrow of the View tab's Display group. Thanks to @cloydcc-dev for the suggestion.
- Properties > Line width for the drawing's own lines (Edit objects, CAD mode): see the width of the selected lines and type a new one.

## 1.15.19 (es)

**Novedades**
- Ver > Mostrar grosores de línea: desactívelo para dibujar cada línea fina en pantalla, como hacen los programas de CAD con los grosores de línea ocultos. La impresión, la exportación y el archivo conservan los anchos de línea reales. También en Preferencias y en la flecha del grupo Visualización de la pestaña Ver. Gracias a @cloydcc-dev por la sugerencia.
- Propiedades > Grosor de línea para las líneas propias del dibujo (Editar objetos, modo CAD): vea el grosor de las líneas seleccionadas y escriba uno nuevo.

## 1.15.19 (it)

**Novità**
- Visualizza > Mostra spessori di linea: disattivalo per disegnare ogni linea sottile sullo schermo, come fanno i programmi CAD con gli spessori di linea nascosti. Stampa, esportazione e file mantengono le larghezze reali delle linee. Anche nelle Preferenze e nella freccia del gruppo Visualizzazione della scheda Visualizza. Grazie a @cloydcc-dev per il suggerimento.
- Proprietà > Spessore linea per le linee del disegno stesso (Modifica oggetti, modalità CAD): vedi lo spessore delle linee selezionate e digitane uno nuovo.

## 1.15.18

**Fixed**
- The page list keeps the thumbnails of your open documents when you switch tabs: only documents open in a tab count toward its limit.

## 1.15.18 (es)

**Correcciones**
- La lista de páginas conserva las miniaturas de sus documentos abiertos al cambiar de pestaña: solo cuentan para su límite los documentos abiertos en una pestaña.

## 1.15.18 (it)

**Correzioni**
- L'elenco delle pagine conserva le miniature dei documenti aperti quando cambi scheda: solo i documenti aperti in una scheda contano per il suo limite.

## 1.15.17

**Fixed**
- A crash that could happen while a background task was running (scanning, finding scanners, recognizing text, exporting, comparing documents) after you had closed a window or dialog.

## 1.15.17 (es)

**Correcciones**
- Un cierre inesperado que podía ocurrir mientras una tarea en segundo plano estaba en curso (escanear, buscar escáneres, reconocer texto, exportar, comparar documentos) después de cerrar una ventana o un cuadro de diálogo.

## 1.15.17 (it)

**Correzioni**
- Un arresto anomalo che poteva verificarsi mentre un'attività in background era in corso (scansione, ricerca degli scanner, riconoscimento del testo, esportazione, confronto di documenti) dopo aver chiuso una finestra o una finestra di dialogo.

## 1.15.16

**Changed**
- Undo now keeps your last 100 steps (it kept 30).

## 1.15.16 (es)

**Cambios**
- Deshacer ahora conserva sus últimos 100 pasos (conservaba 30).

## 1.15.16 (it)

**Modifiche**
- Annulla ora conserva gli ultimi 100 passaggi (ne conservava 30).

## 1.15.15

**Fixed**
- Numbered dots: a setting changed in Properties while you place dots (such as Number inside the dot) now goes to the next dots. Before, it changed only the dot just placed, and the next one went back to the old setting.
- The number inside a filled dot is drawn in the text color you choose. Ticking Number inside the dot on a filled dot makes black text white, and you can pick any color.

**Changed**
- The Dot tool is now called Numbered dot, and its tooltip says each click places the next number. To count items by group with totals, use Count.

## 1.15.15 (es)

**Correcciones**
- Puntos numerados: un ajuste cambiado en Propiedades mientras coloca puntos (como Número dentro del punto) ahora se aplica a los puntos siguientes. Antes solo cambiaba el punto recién colocado, y el siguiente volvía al ajuste anterior.
- El número dentro de un punto relleno se dibuja en el color de texto que elija. Al marcar Número dentro del punto en un punto relleno, el texto negro pasa a blanco, y puede elegir cualquier color.

**Cambios**
- La herramienta Punto ahora se llama Punto numerado, y su descripción dice que cada clic coloca el número siguiente. Para contar elementos por grupo con totales, use Conteo.

## 1.15.15 (it)

**Correzioni**
- Punti numerati: un'impostazione cambiata in Proprietà mentre metti i punti (come Numero dentro il punto) ora vale per i punti successivi. Prima cambiava solo il punto appena messo, e il successivo tornava all'impostazione precedente.
- Il numero dentro un punto pieno è disegnato nel colore del testo che scegli. Spuntando Numero dentro il punto su un punto pieno, il testo nero diventa bianco, e puoi scegliere qualsiasi colore.

**Modifiche**
- Lo strumento Punto ora si chiama Punto numerato, e la sua descrizione dice che ogni clic mette il numero successivo. Per contare elementi per gruppo con i totali, usa Conteggio.

## 1.15.14

**Fixed**
- A rare crash when the Scan window was closed while it was still looking for scanners or talking to one.

## 1.15.14 (es)

**Correcciones**
- Un cierre inesperado poco frecuente al cerrar la ventana Escanear mientras aún buscaba escáneres o se comunicaba con uno.

## 1.15.14 (it)

**Correzioni**
- Una chiusura improvvisa rara chiudendo la finestra Scansiona mentre stava ancora cercando gli scanner o comunicando con uno.

## 1.15.13

**Fixed**
- A selected Count marker now shows a dashed box around it and its number: before, nothing showed it was selected. A selection's outline is drawn blue over white, so it shows on blue markups too. Thanks to @cloydcc-dev for reporting it.

## 1.15.13 (es)

**Correcciones**
- Un marcador de Conteo seleccionado ahora muestra un recuadro discontinuo alrededor de él y de su número: antes, nada indicaba que estaba seleccionado. El contorno de una selección se dibuja en azul sobre blanco, para que se vea también sobre marcas azules. Gracias a @cloydcc-dev por informarlo.

## 1.15.13 (it)

**Correzioni**
- Un indicatore di Conteggio selezionato ora mostra un riquadro tratteggiato attorno a sé e al suo numero: prima, nulla indicava che era selezionato. Il contorno di una selezione è disegnato in blu su bianco, così si vede anche sulle annotazioni blu. Grazie a @cloydcc-dev per la segnalazione.

## 1.15.12

**Fixed**
- Zooming in the middle of drawing a polygon (or a polyline or a measurement) moved what was drawn so far: it now stays where you clicked.
- Holding Shift while dragging a corner of a polygon now keeps both of its sides straight: near a square corner it lands there, and elsewhere it slides along a straight side, making it longer or shorter. Before, only one side was kept straight.

## 1.15.12 (es)

**Correcciones**
- Hacer zoom mientras dibujaba un polígono (o una polilínea o una medición) movía lo ya dibujado: ahora se queda donde hizo clic.
- Mantener Shift al arrastrar un vértice de un polígono ahora mantiene rectos sus dos lados: cerca de una esquina en ángulo recto se coloca allí, y en otro lugar se desliza sobre un lado recto, alargándolo o acortándolo. Antes solo un lado quedaba recto.

## 1.15.12 (it)

**Correzioni**
- Lo zoom mentre si disegnava un poligono (o una polilinea o una misura) spostava quanto già disegnato: ora resta dove hai fatto clic.
- Tenere premuto Shift mentre trascini un vertice di un poligono ora mantiene dritti entrambi i lati: vicino a un angolo retto si posiziona lì, altrove scorre lungo un lato dritto, allungandolo o accorciandolo. Prima solo un lato restava dritto.

## 1.15.11

**New**
- Ctrl+W closes the tab (Ctrl+F4 still does too). If the document has unsaved changes, KanzonasPDF asks first.

## 1.15.11 (es)

**Novedades**
- Ctrl+W cierra la pestaña (Ctrl+F4 también sigue haciéndolo). Si el documento tiene cambios sin guardar, KanzonasPDF pregunta antes.

## 1.15.11 (it)

**Novità**
- Ctrl+W chiude la scheda (anche Ctrl+F4 continua a farlo). Se il documento ha modifiche non salvate, KanzonasPDF chiede prima.

## 1.15.10

**New**
- Back and Forward: the arrows beside Undo and Redo, Alt+Left / Alt+Right, View > Go to, or right-click the page. They take you back to where you were before a link, a bookmark, Go to page or a search, also in another document (opened again if you closed it).
- Ctrl+middle-click a link to open its place in a new tab (view only) or in the split view, without leaving where you are. KanzonasPDF asks which the first time; Preferences > Mouse changes it.
- The Hand only views now: it's always a hand, moves the page, follows links and fills in forms, and never selects or changes anything. Use Select (V) to select text and markups.
- Hold Space and drag to move the page with any tool.

**Fixed**
- A link to a page sometimes showed the bottom of that page and mostly the next one: links through named destinations, and links to sheets turned a quarter, now land where they say.
- A rare crash when changing the theme (View > Theme) soon after closing a dialog.

## 1.15.10 (es)

**Novedades**
- Atrás y Adelante: las flechas junto a Deshacer y Rehacer, Alt+Left / Alt+Right, Ver > Ir a, o clic derecho en la página. Lo llevan de vuelta a donde estaba antes de un vínculo, un marcador, Ir a la página o una búsqueda, también en otro documento (que se abre de nuevo si lo cerró).
- Ctrl+clic central en un vínculo abre su lugar en una pestaña nueva (de solo lectura) o en la vista dividida, sin dejar donde está. KanzonasPDF pregunta cuál la primera vez; Preferencias > Mouse lo cambia.
- La Mano ahora solo sirve para ver: siempre es una mano, mueve la página, sigue vínculos y rellena formularios, y nunca selecciona ni cambia nada. Use Seleccionar (V) para seleccionar texto y marcas.
- Mantenga presionada la barra espaciadora y arrastre para mover la página con cualquier herramienta.

**Correcciones**
- Un vínculo a una página a veces mostraba el final de esa página y casi toda la siguiente: los vínculos a destinos con nombre y a hojas giradas un cuarto de vuelta ahora llevan a donde indican.
- Un cierre inesperado poco frecuente al cambiar el tema (Ver > Tema) poco después de cerrar un cuadro de diálogo.

## 1.15.10 (it)

**Novità**
- Indietro e Avanti: le frecce accanto ad Annulla e Ripeti, Alt+Left / Alt+Right, Visualizza > Vai a, o clic destro sulla pagina. Ti riportano dov'eri prima di un collegamento, un segnalibro, Vai a pagina o una ricerca, anche in un altro documento (riaperto se l'avevi chiuso).
- Ctrl+clic centrale su un collegamento ne apre il punto in una nuova scheda (di sola lettura) o nella vista divisa, senza lasciare il punto in cui sei. KanzonasPDF chiede quale la prima volta; Preferenze > Mouse lo cambia.
- La Mano ora serve solo a guardare: è sempre una mano, sposta la pagina, segue i collegamenti e compila i moduli, e non seleziona né cambia mai nulla. Usa Seleziona (V) per selezionare testo e annotazioni.
- Tieni premuta la barra spaziatrice e trascina per spostare la pagina con qualsiasi strumento.

**Correzioni**
- Un collegamento a una pagina a volte mostrava il fondo di quella pagina e quasi tutta la successiva: i collegamenti a destinazioni con nome e ai fogli ruotati di un quarto di giro ora portano dove indicano.
- Una chiusura improvvisa rara cambiando il tema (Visualizza > Tema) poco dopo aver chiuso una finestra di dialogo.

## 1.15.9

**New**
- Count: set it up in Properties before you click. Pick or type a Group (Smoke detectors, Speakers...), start a New count (Count 2, Count 3... beginning at 1, each in a color of its own), and choose the Layer its markers go on. Going back to a group gives the next markers its color, size and layer. Properties shows the next marker's number while you click.
- Count: Keep the numbers in order (on unless you switch it off): deleting a marker numbers the rest of its group 1, 2, 3... again, so there are no gaps. Select a marker to change its group or number; right-click > Renumber group closes old gaps.
- Count: Properties says when a group's numbers have gaps or repeats (for example after a marker was deleted in another PDF viewer), with a Renumber button beside it.

**Fixed**
- The Count tool's group couldn't be changed: every marker went into "Count 1".

**Thanks** to @cloydcc-dev for asking for all of this (#107).

## 1.15.9 (es)

**Novedades**
- Conteo: prepárelo en Propiedades antes de hacer clic. Elija o escriba un Grupo (Detectores de humo, Altavoces...), empiece un Nuevo conteo (Conteo 2, Conteo 3... desde el 1, cada uno con su propio color) y elija la Capa en la que van sus marcadores. Al volver a un grupo, los siguientes marcadores toman su color, tamaño y capa. Propiedades muestra el número del siguiente marcador mientras hace clic.
- Conteo: Mantener los números en orden (activado salvo que lo desactive): al eliminar un marcador, los demás de su grupo se numeran de nuevo 1, 2, 3..., sin huecos. Seleccione un marcador para cambiar su grupo o su número; clic derecho > Renumerar el grupo cierra los huecos que ya había.
- Conteo: Propiedades avisa cuando los números de un grupo tienen huecos o repetidos (por ejemplo, después de eliminar un marcador en otro visor de PDF), con un botón Renumerar al lado.

**Correcciones**
- No se podía cambiar el grupo de la herramienta Conteo: todos los marcadores iban a "Count 1".

**Gracias** a @cloydcc-dev por pedir todo esto (#107).

## 1.15.9 (it)

**Novità**
- Conteggio: preparalo in Proprietà prima di fare clic. Scegli o scrivi un Gruppo (Rilevatori di fumo, Altoparlanti...), inizia un Nuovo conteggio (Conteggio 2, Conteggio 3... a partire da 1, ognuno con un colore suo) e scegli il Livello su cui vanno i suoi indicatori. Tornando a un gruppo, i prossimi indicatori prendono il suo colore, la sua dimensione e il suo livello. Proprietà mostra il numero del prossimo indicatore mentre fai clic.
- Conteggio: Mantieni i numeri in ordine (attivo a meno che non lo disattivi): eliminando un indicatore, gli altri del suo gruppo vengono numerati di nuovo 1, 2, 3..., senza buchi. Seleziona un indicatore per cambiarne il gruppo o il numero; clic destro > Rinumera il gruppo chiude i buchi già presenti.
- Conteggio: Proprietà avvisa quando i numeri di un gruppo hanno buchi o ripetizioni (per esempio dopo aver eliminato un indicatore in un altro visualizzatore PDF), con un pulsante Rinumera accanto.

**Correzioni**
- Il gruppo dello strumento Conteggio non si poteva cambiare: tutti gli indicatori andavano in "Count 1".

**Grazie** a @cloydcc-dev per aver chiesto tutto questo (#107).

## 1.15.8

**Fixed**
- Selecting text shows the text cursor (not in the CAD mouse mode). The Hand tool's pointer is now the arrow until it's over text, where it becomes the text cursor: drag from text to select it, as in Adobe Acrobat; drag anywhere else to move the page. To have the Hand only move the page, switch off "Dragging from text with the Hand selects the text" in Preferences > Mouse.
- In the Standard (Select) mouse mode nothing drags the page any more: picking the Hand there gives Select. Hold the mouse wheel down to move the page, or switch to the Hand mouse mode.

## 1.15.8 (es)

**Correcciones**
- Al seleccionar texto se ve el cursor de texto (no en el modo del mouse CAD). El puntero de la herramienta Mano ahora es la flecha hasta que pasa sobre el texto, donde se convierte en el cursor de texto: arrastre desde el texto para seleccionarlo, como en Adobe Acrobat; arrastre en cualquier otro lugar para mover la página. Para que la Mano solo mueva la página, desactive "Arrastrar desde el texto con la Mano selecciona el texto" en Preferencias > Mouse.
- En el modo del mouse Estándar (Seleccionar) ya nada arrastra la página: elegir la Mano allí da Seleccionar. Mantenga presionada la rueda del mouse para mover la página, o cambie al modo del mouse Mano.

## 1.15.8 (it)

**Correzioni**
- Quando selezioni il testo compare il cursore di testo (non nella modalità del mouse CAD). Il puntatore dello strumento Mano ora è la freccia finché non passa sopra il testo, dove diventa il cursore di testo: trascina dal testo per selezionarlo, come in Adobe Acrobat; trascina in qualsiasi altro punto per spostare la pagina. Perché la Mano sposti soltanto la pagina, disattiva "Trascinare dal testo con la Mano seleziona il testo" in Preferenze > Mouse.
- Nella modalità del mouse Standard (Seleziona) niente trascina più la pagina: scegliere la Mano lì dà Seleziona. Tieni premuta la rotellina del mouse per spostare la pagina, oppure passa alla modalità del mouse Mano.

## 1.15.7

**Fixed**
- Outlook shows PDF attachments in its preview again. KanzonasPDF no longer puts in a PDF previewer of its own, which Outlook couldn't use; previews come from Windows' own PDF previewer, as before 1.14.1. File Explorer still shows KanzonasPDF's page thumbnails.

## 1.15.7 (es)

**Correcciones**
- Outlook vuelve a mostrar los PDF adjuntos en su vista previa. KanzonasPDF ya no añade un visor de PDF propio, que Outlook no podía usar; las vistas previas las da el visor de PDF de Windows, como antes de la 1.14.1. El Explorador de archivos sigue mostrando las miniaturas de página de KanzonasPDF.

## 1.15.7 (it)

**Correzioni**
- Outlook mostra di nuovo i PDF allegati nella sua anteprima. KanzonasPDF non aggiunge più un visualizzatore PDF suo, che Outlook non poteva usare; le anteprime vengono dal visualizzatore PDF di Windows, come prima della 1.14.1. Esplora file mostra ancora le miniature delle pagine di KanzonasPDF.

## 1.15.6

**New**
- Properties shows the rotation of the page's own pictures and groups: type an angle to turn one to it. For lines and shapes, Rotate by turns them by the degrees typed.

**Fixed**
- Snapping now finds a picture's corners, edge middles and center, so a CAD command's base point can be a picture's corner.

## 1.15.6 (es)

**Novedades**
- Propiedades muestra la rotación de las imágenes y los grupos propios de la página: escriba un ángulo para girar uno hasta él. Para líneas y formas, Girar las gira los grados escritos.

**Correcciones**
- El ajuste ahora encuentra las esquinas, los puntos medios de los bordes y el centro de una imagen, así que el punto base de un comando CAD puede ser la esquina de una imagen.

## 1.15.6 (it)

**Novità**
- Proprietà mostra la rotazione delle immagini e dei gruppi della pagina: digita un angolo per ruotarne uno fino a quello. Per linee e forme, Ruota di le ruota dei gradi digitati.

**Correzioni**
- L'aggancio ora trova gli angoli, i punti medi dei lati e il centro di un'immagine, così il punto base di un comando CAD può essere l'angolo di un'immagine.

## 1.15.5

**Fixed**
- Windows: Update now could quit without updating once File Explorer had shown a PDF thumbnail (Windows kept a file in use in its "COM Surrogate"). The setup now closes it, and if an update ever doesn't finish, KanzonasPDF tells you the next time it starts.

## 1.15.5 (es)

**Correcciones**
- Windows: Actualizar ahora podía cerrarse sin actualizar después de que el Explorador mostrara la miniatura de un PDF (Windows mantenía un archivo en uso en su "COM Surrogate"). Ahora el instalador lo cierra, y si alguna vez una actualización no termina, KanzonasPDF se lo dice la próxima vez que se inicia.

## 1.15.5 (it)

**Correzioni**
- Windows: Aggiorna ora poteva chiudersi senza aggiornare dopo che Esplora file aveva mostrato la miniatura di un PDF (Windows teneva un file in uso nel suo "COM Surrogate"). Ora il programma di installazione lo chiude, e se un aggiornamento non si completa, KanzonasPDF te lo dice al successivo avvio.

## 1.15.4

**New**
- Edit objects (and CAD mode): turn the page's own pictures, shapes and groups by dragging the round handle above them (Shift for 15° steps), or right-click > Rotate by an angle... and type the degrees.

## 1.15.4 (es)

**Novedades**
- Editar objetos (y el modo CAD): gire las imágenes, formas y grupos propios de la página arrastrando el controlador redondo que tienen encima (Shift para pasos de 15°), o haga clic con el botón derecho > Girar un ángulo... y escriba los grados.

## 1.15.4 (it)

**Novità**
- Modifica oggetti (e la modalità CAD): ruota le immagini, le forme e i gruppi della pagina trascinando la maniglia rotonda sopra di essi (Shift per passi di 15°), o fai clic con il tasto destro > Ruota di un angolo... e digita i gradi.

## 1.15.3

**New**
- The Image tool takes SVG drawings. They go into the page as real lines and shapes, so they stay sharp at any zoom, and Edit objects moves, resizes or ungroups them.
- CAD mode: hold Shift or Ctrl while clicking a command's point to keep it straight across or straight up and down from the point before, for example a level or upright mirror line.

**Fixed**
- CAD mode: Mirror's "delete the originals?" (and Align's "scale it?") now takes a typed Yes or No, or just Y or N. Enter alone still means No.

## 1.15.3 (es)

**Novedades**
- La herramienta Imagen acepta dibujos SVG. Entran en la página como líneas y formas reales, así que se ven nítidos con cualquier zoom, y Editar objetos los mueve, cambia de tamaño o desagrupa.
- Modo CAD: mantenga presionada Mayús o Ctrl al hacer clic en el punto de un comando para que quede justo en horizontal o en vertical respecto al punto anterior, por ejemplo un eje de simetría horizontal o vertical.

**Correcciones**
- Modo CAD: «¿eliminar los originales?» de Simetría (y «¿escalarlo?» de Alinear) ahora acepta Sí o No escritos, o solo S o N. Enter solo sigue siendo No.

## 1.15.3 (it)

**Novità**
- Lo strumento Immagine accetta disegni SVG. Entrano nella pagina come linee e forme vere, quindi restano nitidi a qualsiasi zoom, e Modifica oggetti li sposta, ridimensiona o separa.
- Modalità CAD: tieni premuto Maiusc o Ctrl mentre fai clic sul punto di un comando per tenerlo esattamente in orizzontale o in verticale rispetto al punto precedente, per esempio una linea di specchiatura orizzontale o verticale.

**Correzioni**
- Modalità CAD: «eliminare gli originali?» di Specchia (e «scalarlo?» di Allinea) ora accetta Sì o No digitati, o solo S o N. Invio da solo significa ancora No.

## 1.15.2

**Fixed**
- Inserting, deleting and moving pages no longer pauses to tidy up memory when it doesn't need to. With a large drawing open or after a long session, that pause could take a second or more.

## 1.15.2 (es)

**Correcciones**
- Insertar, eliminar y mover páginas ya no se detiene a ordenar la memoria cuando no hace falta. Con un dibujo grande abierto o después de una sesión larga, esa pausa podía durar un segundo o más.

## 1.15.2 (it)

**Correzioni**
- Inserire, eliminare e spostare pagine non si ferma più a riordinare la memoria quando non serve. Con un disegno grande aperto o dopo una sessione lunga, quella pausa poteva durare un secondo o più.

## 1.15.1

**Fixed**
- CAD mode: Escape now always unselects everything, also right after you type a letter for the command line or click empty space to start a selection box.
- Align to first selected (and to last selected) now goes by the order you selected things in. Before, it used the order they were drawn in the file, and markups always counted before the page's own objects.

## 1.15.1 (es)

**Correcciones**
- Modo CAD: Escape ahora siempre quita toda la selección, también justo después de escribir una letra para la línea de comandos o de hacer clic en un espacio vacío para empezar un cuadro de selección.
- Alinear con la primera seleccionada (y con la última) ahora sigue el orden en que seleccionó los elementos. Antes usaba el orden en que estaban dibujados en el archivo, y las marcas siempre contaban antes que los objetos propios de la página.

## 1.15.1 (it)

**Correzioni**
- Modalità CAD: Esc ora annulla sempre tutta la selezione, anche subito dopo aver scritto una lettera per la riga di comando o aver fatto clic su uno spazio vuoto per iniziare un riquadro di selezione.
- Allinea alla prima selezionata (e all'ultima) ora segue l'ordine in cui hai selezionato gli elementi. Prima usava l'ordine in cui erano disegnati nel file, e le annotazioni contavano sempre prima degli oggetti della pagina.

## 1.15

**New**
- Change the colors of the page's own drawing and text: with Edit objects (or in CAD mode), select shapes or text, right-click and choose Line color, Fill color or Text color. Each word keeps its font and style, and Ctrl+Z undoes it in one step.
- A version that was never released on its own now has its notes included in the next one, so the update box shows everything that changed.

## 1.15 (es)

**Novedades**
- Cambie los colores del dibujo y el texto propios de la página: con Editar objetos (o en el modo CAD), seleccione formas o texto, haga clic con el botón derecho y elija Color de línea, Color de relleno o Color del texto. Cada palabra conserva su fuente y su estilo, y Ctrl+Z lo deshace en un solo paso.
- Una versión que nunca se publicó por separado ahora incluye sus notas en la siguiente, para que el cuadro de actualización muestre todo lo que cambió.

## 1.15 (it)

**Novità**
- Cambia i colori del disegno e del testo propri della pagina: con Modifica oggetti (o in modalità CAD), seleziona forme o testo, fai clic con il tasto destro e scegli Colore linea, Colore riempimento o Colore testo. Ogni parola mantiene il suo carattere e il suo stile, e Ctrl+Z lo annulla in un solo passo.
- Una versione che non è mai stata pubblicata da sola ora ha le sue note incluse nella successiva, così la finestra degli aggiornamenti mostra tutto ciò che è cambiato.

## 1.14.2

**Fixed**
- The Pages panel's lock button shows a lock icon that follows the light or dark theme, instead of an emoji.
- Behind the scenes: a cleanup of the program's code, found by the new check for leftovers and sloppy code (nothing else changes in how it works).

## 1.14.2 (es)

**Correcciones**
- El botón de bloqueo del panel Páginas muestra un icono de candado que sigue el tema claro u oscuro, en lugar de un emoji.
- Internamente: una limpieza del código del programa, encontrada por la nueva comprobación de restos y código descuidado (nada más cambia en su funcionamiento).

## 1.14.2 (it)

**Correzioni**
- Il pulsante di blocco del pannello Pagine mostra un'icona a lucchetto che segue il tema chiaro o scuro, al posto di un'emoji.
- Dietro le quinte: una pulizia del codice del programma, trovata dal nuovo controllo di residui e codice trascurato (nient'altro cambia nel suo funzionamento).

## 1.14.1

**New**
- Windows File Explorer shows a PDF's first page as its thumbnail, instead of the KanzonasPDF icon, and its pages in the Preview pane (Alt+P), once KanzonasPDF is your default PDF app. A PDF with a password keeps the icon. Folders you've already opened may show icons until Windows redraws them (or clear "Thumbnails" in Disk Cleanup).

## 1.14.1 (es)

**Novedades**
- El Explorador de archivos de Windows muestra la primera página de un PDF como su miniatura, en lugar del icono de KanzonasPDF, y sus páginas en el panel de vista previa (Alt+P), cuando KanzonasPDF es su aplicación predeterminada para PDF. Un PDF con contraseña conserva el icono. Las carpetas que ya abrió pueden mostrar iconos hasta que Windows las vuelva a dibujar (o limpie "Miniaturas" en el Liberador de espacio en disco).

## 1.14.1 (it)

**Novità**
- Esplora file di Windows mostra la prima pagina di un PDF come miniatura, al posto dell'icona di KanzonasPDF, e le sue pagine nel riquadro di anteprima (Alt+P), quando KanzonasPDF è la tua app predefinita per i PDF. Un PDF con password mantiene l'icona. Le cartelle che hai già aperto possono mostrare le icone finché Windows non le ridisegna (oppure elimina le "Anteprime" con Pulizia disco).

## 1.14

**New**
- Dot (Markup tab, shortcut B): one click places a numbered dot, filled or outline only, as for the elevation points on a floor plan. Show its number, a text or both beside it (right, below, left or above), or the number inside the dot; new dots and copies take the next number.

**Thanks** to @fexxdev, who made the Dot tool.

## 1.14 (es)

**Novedades**
- Punto (pestaña Marcas, atajo B): un clic coloca un punto numerado, relleno o solo con contorno, como las cotas de un plano. Muestre su número, un texto o ambos junto a él (a la derecha, debajo, a la izquierda o encima), o el número dentro del punto; los puntos nuevos y las copias toman el número siguiente.

**Gracias** a @fexxdev, que hizo la herramienta Punto.

## 1.14 (it)

**Novità**
- Punto (scheda Annotazioni, scorciatoia B): un clic mette un punto numerato, pieno o solo bordo, come le quote su una pianta. Mostra il numero, un testo o entrambi accanto (a destra, sotto, a sinistra o sopra), oppure il numero dentro il punto; i nuovi punti e le copie prendono il numero successivo.

**Grazie** a @fexxdev, che ha creato lo strumento Punto.

## 1.13.2

**Fixed**
- Edit text and Edit objects see all of the page's text on a turned page: a line of text written right to left could lose its first letter, or vanish from them altogether after a drawing elsewhere on the page was deleted (the text itself was never lost).

## 1.13.2 (es)

**Correcciones**
- Editar texto y Editar objetos ven todo el texto de la página en una página girada: una línea de texto escrita de derecha a izquierda podía perder su primera letra, o desaparecer por completo para ellos después de eliminar un dibujo en otra parte de la página (el texto en sí nunca se perdía).

## 1.13.2 (it)

**Correzioni**
- Modifica testo e Modifica oggetti vedono tutto il testo della pagina su una pagina ruotata: una riga di testo scritta da destra a sinistra poteva perdere la prima lettera, o sparire del tutto per loro dopo l'eliminazione di un disegno altrove nella pagina (il testo in sé non andava mai perso).

## 1.13.1

**New**
- Arrange > Group (Ctrl+Shift+G) now groups the page's own lines, shapes, pictures and text too (Edit objects or CAD mode): a click on any of it selects the whole group, and it moves, copies and deletes as one object. Ungroup takes it apart again. Markups and the page's own objects can't be one group: with both selected, Group is grayed out and its tooltip says why.
- Text boxes and callouts fit their text: the box keeps its width and grows or shrinks to its text when it's made, when the text or font size changes, and when you drag its side. Right-click > Fit to text fits an existing one; "Fit the box to its text" in Properties turns it on or off and is part of the tool's style. Dragging its top or bottom sets a height of your own. (Issue #90)

**Fixed**
- Undo and Redo no longer unselect what you had selected.

**Thanks** to @fexxdev for the Italian translation in 1.13 and the fixes in 1.12.2, and to @hellensvard for suggesting callouts that fit their text (#90).

## 1.13.1 (es)

**Novedades**
- Organizar > Agrupar (Ctrl+Shift+G) ahora también agrupa las líneas, formas, imágenes y texto propios de la página (Editar objetos o modo CAD): un clic en cualquier parte selecciona el grupo entero, y se mueve, se copia y se elimina como un solo objeto. Desagrupar lo vuelve a separar. Las marcas y los objetos propios de la página no pueden ser un mismo grupo: con ambos seleccionados, Agrupar queda en gris y su información sobre herramientas dice por qué.
- Los cuadros de texto y las llamadas se ajustan a su texto: el cuadro mantiene su ancho y crece o se encoge con su texto al crearlo, al cambiar el texto o el tamaño de fuente y al arrastrar su lado. Botón derecho > Ajustar al texto ajusta uno existente; "Ajustar el cuadro a su texto" en Propiedades lo activa o desactiva y forma parte del estilo de la herramienta. Arrastrar su borde superior o inferior le da una altura propia. (Incidencia #90)

**Correcciones**
- Deshacer y Rehacer ya no quitan la selección.

**Gracias** a @fexxdev por la traducción al italiano de 1.13 y las correcciones de 1.12.2, y a @hellensvard por sugerir llamadas que se ajustan a su texto (#90).

## 1.13.1 (it)

**Novità**
- Disponi > Raggruppa (Ctrl+Shift+G) ora raggruppa anche le linee, le forme, le immagini e il testo propri della pagina (Modifica oggetti o modalità CAD): un clic su un punto qualsiasi seleziona l'intero gruppo, che si sposta, si copia e si elimina come un unico oggetto. Separa lo divide di nuovo. Le annotazioni e gli oggetti propri della pagina non possono formare un unico gruppo: se li selezioni insieme, Raggruppa è disattivato e il suo suggerimento spiega perché.
- Le caselle di testo e i richiami si adattano al testo: il riquadro mantiene la larghezza e si allarga o si riduce con il testo quando lo crei, quando cambi il testo o la dimensione del carattere e quando trascini un lato. Clic destro > Adatta al testo adatta un riquadro esistente; "Adatta il riquadro al testo" in Proprietà lo attiva o disattiva e fa parte dello stile dello strumento. Trascinando il bordo superiore o inferiore gli dai un'altezza tua. (Segnalazione #90)

**Correzioni**
- Annulla e Ripeti non deselezionano più ciò che avevi selezionato.

**Grazie** a @fexxdev per la traduzione italiana della 1.13 e le correzioni della 1.12.2, e a @hellensvard per aver suggerito i richiami che si adattano al testo (#90).

## 1.13

**New**
- KanzonasPDF in Italian: menus, ribbon, messages and the user manual. Pick Italiano in File > Preferences > General > Language, or leave Automatic and an Italian Windows shows it in Italian; the change shows the next time KanzonasPDF starts.

## 1.13 (es)

**Novedades**
- KanzonasPDF en italiano: menús, cinta, mensajes y el manual del usuario. Elija Italiano en Archivo > Preferencias > General > Idioma, o deje Automático y un Windows en italiano lo muestra en italiano; el cambio se ve la próxima vez que se inicia KanzonasPDF.

## 1.13 (it)

**Novità**
- KanzonasPDF in italiano: menu, barra multifunzione, messaggi e manuale utente. Scegli Italiano in File > Preferenze > Generale > Lingua, oppure lascia Automatica e con Windows in italiano lo vedi in italiano; la modifica vale dal prossimo avvio di KanzonasPDF.

## 1.12.2

**Fixed**
- Recognizing text (OCR) uses less memory again with RapidOCR 1.3 and later.
- PDF/A: an attached file gets the same file type on every computer (a .csv was sometimes marked as an Excel file).
- Closing a text box being edited with spell checking on no longer can crash KanzonasPDF.
- Undo after Save gives back exactly what was there, also after Edit objects or Edit text.
- A file that got shorter since you last had it open opens at its last page instead of failing.
- Accessibility: duplicating a page with a hidden markup no longer leaves two markups sharing one tag.

## 1.12.2 (es)

**Correcciones**
- Reconocer texto (OCR) vuelve a usar menos memoria con RapidOCR 1.3 y posteriores.
- PDF/A: un archivo adjunto recibe el mismo tipo de archivo en todos los equipos (un .csv a veces se marcaba como archivo de Excel).
- Cerrar un cuadro de texto en edición con la revisión ortográfica activada ya no puede cerrar KanzonasPDF.
- Deshacer después de Guardar devuelve exactamente lo que había, también después de Editar objetos o Editar texto.
- Un archivo que se acortó desde la última vez que lo abrió se abre en su última página en lugar de fallar.
- Accesibilidad: duplicar una página con una marca oculta ya no deja dos marcas compartiendo una misma etiqueta.

## 1.12.1

**New**
- CAD mode: drag what's selected to move it (markups and the page's own lines, text and pictures together, one undo step). The pointer shows the four-way arrow over the selection; a drag anywhere else still draws a selection box or lasso.
- Pages > Insert pages from file can make pictures searchable: tick "Make the pictures searchable (recognize text, OCR)" and the pages made from pictures have their text recognized. The choice is remembered, shared with Combine files and Create PDF from images.

**Fixed**
- Layers panel: Show all no longer hides the layers that were already shown.

**Changed**
- The Select tool's pointer is the arrow, not the text cursor. The text cursor shows only with the tools that work on text (Edit text, Add text, Highlight and the other text markups, Redact) and where you type. Dragging over text with Select still selects it.

## 1.12.1 (es)

**Novedades**
- Modo CAD: arrastre lo seleccionado para moverlo (las marcas y las líneas, el texto y las imágenes propios de la página a la vez, en un solo paso de deshacer). El puntero muestra la flecha de cuatro puntas sobre la selección; un arrastre en cualquier otro lugar sigue dibujando un cuadro de selección o un lazo.
- Páginas > Insertar páginas desde archivo puede hacer buscables las imágenes: marque "Hacer las imágenes buscables (reconocer texto, OCR)" y se reconoce el texto de las páginas hechas a partir de imágenes. La elección se recuerda, compartida con Combinar archivos y Crear PDF desde imágenes.

**Correcciones**
- Panel Capas: Mostrar todo ya no oculta las capas que ya se mostraban.

**Cambios**
- El puntero de la herramienta Seleccionar es la flecha, no el cursor de texto. El cursor de texto solo aparece con las herramientas que trabajan con texto (Editar texto, Agregar texto, Resaltar y las demás marcas de texto, Redactar) y donde escribe. Arrastrar sobre el texto con Seleccionar sigue seleccionándolo.

## 1.12

**New** (features from Bluebeam Revu)
- Rulers: View > Rulers (Ctrl+R) along the top and left of the page, in inches, millimeters or points (right-click a ruler). The status bar shows the page size and where the pointer is on the page.
- Reuse switch on the status bar: on, the tool you drew with stays picked; off, it goes back to Select (or Hand) after each markup.
- Split view side by side or top and bottom, showing any open document, with Sync to pan and zoom both together, by page number or by the pages in view: compare a plan with a detail, or two revisions.
- Arrange > Group and Ungroup (Ctrl+Shift+G / Ctrl+Alt+G): grouped markups are selected, moved, restyled, copied and deleted together. They're a standard PDF group, so Acrobat sees it too. Flip horizontally and Flip vertically mirror a markup or a group.
- Markups on layers: make a layer in the Layers panel, choose the layer new markups go on, and right-click markups > Layer to move them. Hiding a layer hides its markups, in other PDF programs too. The Markups list shows and filters by layer.
- Spaces: the Space tool (Measure tab) draws a named area, such as Room 101. The Markups list shows which space each markup is in and filters by space, for punch lists and counts room by room.
- Sets: browse several PDFs (one per sheet, say) as one document without combining them. File > New set... lists them in the Sets panel by sheet number and title, Next and Previous sheet go across the files, and Combine to one PDF makes a single file of them.

**Fixed**
- Moving the page's own text with the arrow keys (or by dragging) onto another line of text no longer deletes that line's letters, and a paragraph moved over other text no longer picks it up and carries it along. The selection stays on the text you selected, and Ctrl+Z undoes a whole series of arrow-key moves at once.
- Moving text that sits at an angle (a diagonal watermark, a tilted label) keeps its angle and its see-through look, and leaves no letters behind. A move that can't be made (redaction marks waiting on the page) no longer unselects the text. The page's own text now stops at the edge of the page (letters moved past it were lost on the next move), and its pictures and shapes can't be moved off the page altogether.
- Markups being placed or moved in the gray around a page now show while you place them: a stamp following the pointer, a box dragged off the page, a markup moved beside it, a polygon's next side.
- Snap to objects works when moving the page's own pictures, shapes and text with Edit objects: they snap to the drawing's line ends and corners too.
- With the Hand tool, dragging a markup moves it (it was only selected).
- Align and Distribute move a group as one item.
- Documents tagged for screen readers: duplicating a page with nothing tagged on it no longer leaves the copy sharing the original's tag entry, and a reply moved to another page with its markup keeps its tag.

## 1.12 (es)

**Novedades** (funciones de Bluebeam Revu)
- Reglas: Ver > Reglas (Ctrl+R) a lo largo de la parte de arriba y de la izquierda de la página, en pulgadas, milímetros o puntos (clic derecho en una regla). La barra de estado muestra el tamaño de la página y dónde está el puntero en ella.
- Interruptor Reutilizar en la barra de estado: activado, la herramienta con la que dibujó sigue elegida; desactivado, vuelve a Seleccionar (o Mano) después de cada marca.
- Vista dividida lado a lado o arriba y abajo, con cualquier documento abierto, y Sincronizar para desplazar y hacer zoom en las dos a la vez, por número de página o por las páginas a la vista: compare un plano con un detalle, o dos revisiones.
- Organizar > Agrupar y Desagrupar (Ctrl+Mayús+G / Ctrl+Alt+G): las marcas agrupadas se seleccionan, mueven, cambian de estilo, copian y eliminan juntas. Son un grupo PDF estándar, así que Acrobat también lo ve. Voltear horizontalmente y Voltear verticalmente reflejan una marca o un grupo.
- Marcas en capas: cree una capa en el panel Capas, elija la capa en la que van las marcas nuevas y haga clic derecho en marcas > Capa para moverlas. Ocultar una capa oculta sus marcas, también en otros programas de PDF. La lista de marcas muestra y filtra por capa.
- Espacios: la herramienta Espacio (pestaña Medir) dibuja un área con nombre, como Habitación 101. La lista de marcas muestra en qué espacio está cada marca y filtra por espacio, para listas de pendientes y conteos habitación por habitación.
- Conjuntos: recorra varios PDF (uno por plano, por ejemplo) como un solo documento sin combinarlos. Archivo > Nuevo conjunto... los muestra en el panel Conjuntos por número y título de plano, Plano siguiente y Plano anterior avanzan a través de los archivos, y Combinar en un PDF hace un solo archivo con ellos.

**Correcciones**
- Mover el texto propio de la página con las flechas del teclado (o arrastrándolo) sobre otra línea de texto ya no borra las letras de esa línea, y un párrafo movido sobre otro texto ya no lo recoge y se lo lleva. La selección se queda en el texto que seleccionó, y Ctrl+Z deshace de una vez toda una serie de movimientos con las flechas.
- Mover texto en ángulo (una marca de agua en diagonal, una etiqueta inclinada) conserva su ángulo y su transparencia, y no deja letras atrás. Un movimiento que no se puede hacer (marcas de redacción pendientes en la página) ya no deja el texto sin seleccionar. El texto propio de la página ahora se detiene en el borde de la página (las letras que pasaban de él se perdían en el siguiente movimiento), y sus imágenes y formas no se pueden sacar del todo de la página.
- Las marcas que se colocan o se mueven en el gris alrededor de una página ahora se ven mientras las coloca: un sello que sigue al puntero, un cuadro arrastrado fuera de la página, una marca movida a su lado, el lado siguiente de un polígono.
- Ajustar a objetos funciona al mover las imágenes, formas y texto propios de la página con Editar objetos: también se ajustan a los extremos de línea y las esquinas del dibujo.
- Con la herramienta Mano, arrastrar una marca la mueve (solo se seleccionaba).
- Alinear y Distribuir mueven un grupo como un solo elemento.
- Documentos etiquetados para lectores de pantalla: duplicar una página sin nada etiquetado ya no deja la copia compartiendo la entrada de etiquetas del original, y una respuesta movida a otra página con su marca conserva su etiqueta.

## 1.11.1

**New**
- Create PDF from images and Combine files can make pictures of text searchable: tick "Make the pictures searchable (recognize text, OCR)" and the text on the pages made from pictures is recognized, so you can find and select its words. The PDF is saved with it, and the choice is remembered.

**Fixed**
- Pages panel: dragging a page now scrolls the list when you hold it near the top or bottom, or just above or below the list, so a page can go anywhere in a long document.

## 1.11.1 (es)

**Novedades**
- Crear PDF desde imágenes y Combinar archivos pueden hacer buscables las imágenes de texto: marque "Hacer las imágenes buscables (reconocer texto, OCR)" y se reconoce el texto de las páginas hechas a partir de imágenes, así que puede buscar y seleccionar sus palabras. El PDF se guarda con él, y la elección se recuerda.

**Correcciones**
- Panel Páginas: al arrastrar una página, la lista ahora se desplaza si la mantiene cerca de la parte de arriba o de abajo, o justo por encima o por debajo de la lista, así que una página puede ir a cualquier lugar de un documento largo.

## 1.11

**New**
- Markups anywhere in the gray around a page: put comments, pictures or other sheets beside a drawing (to put a plan spread over several sheets back together). The page makes room for them, nothing gets covered, and Fit page and markups shows it all. They're saved but don't print unless you choose (on the same sheet, or on an extra sheet so the drawing stays at scale), and other PDF programs don't show them. Review > Show markups on the page and Show markups outside pages hide one or the other; Sanitize document and Remove hidden information take them out.
- Pages > Add space around page: make a page bigger on the sides you choose, with the drawing and everything on it staying where it is. The new space is real page: it prints and shows everywhere, so it's room for comments or for pasting in other sheets to make one combined plan.
- What you just drew stays selected, so Properties changes it right away; right-click a markup > Set as Default to use its style for the next ones. The Properties title shows plainly whether you're changing a markup or a tool's style.
- The first time something you draw, paste or move goes outside a page, KanzonasPDF asks how markups outside pages should print (Don't ask again stops the question).
- The document tab in front is easier to spot: a blue line along its top, the other tabs' names a little dimmer.

**Fixed**
- Opacity now works on pictures and on Capture area's pasted captures (they stayed solid).
- The opacity slider applies when you click its track or use the arrow keys, not only when you drag it.
- After Crop pages, a box or callout no longer jumps when you edit it.
- Security: PDF reading updated (PyMuPDF 2.1, with MuPDF 1.28.6).

## 1.11 (es)

**Novedades**
- Marcas en cualquier lugar del gris alrededor de una página: ponga comentarios, imágenes u otros planos junto a un dibujo (para volver a juntar un plano repartido en varias hojas). La página deja espacio para ellos, nada queda tapado y Ajustar página y marcas lo muestra todo. Se guardan pero no se imprimen salvo que lo elija (en la misma hoja, o en una hoja extra para que el plano conserve su escala), y otros programas de PDF no los muestran. Revisar > Mostrar marcas en la página y Mostrar marcas fuera de las páginas ocultan unas u otras; Sanear documento y Quitar la información oculta las quitan.
- Páginas > Agregar espacio alrededor de la página: agrande una página por los lados que elija, con el dibujo y todo lo que tiene quedándose donde está. El espacio nuevo es página real: se imprime y se ve en todas partes, así que sirve para comentarios o para pegar otros planos y formar un solo plano combinado.
- Lo que acaba de dibujar queda seleccionado, así que Propiedades lo cambia enseguida; clic con el botón derecho en una marca > Establecer como predeterminado para usar su estilo en las siguientes. El título de Propiedades muestra claramente si cambia una marca o el estilo de una herramienta.
- La primera vez que algo que dibuja, pega o mueve sale de una página, KanzonasPDF pregunta cómo deben imprimirse las marcas fuera de las páginas (No volver a preguntar hace que no pregunte más).
- La pestaña del documento de delante se distingue mejor: una línea azul arriba y los nombres de las demás pestañas un poco más tenues.

**Correcciones**
- La opacidad ya funciona en las imágenes y en las capturas pegadas de Capturar área (se quedaban sólidas).
- El control de opacidad se aplica al hacer clic en su guía o al usar las flechas del teclado, no solo al arrastrarlo.
- Después de Recortar páginas, un cuadro o una llamada ya no salta al editarlo.
- Seguridad: lectura de PDF actualizada (PyMuPDF 2.1, con MuPDF 1.28.6).

## 1.10.1

**Fixed**
- Links to other files, as in a drawing index: when the linked file isn't where the link says (the index was made on another person's computer, or the folders were moved or synced somewhere else), KanzonasPDF looks for it from the folder of the document you're reading and opens it; the status bar says which file it opened. If it can't find it, the message says so and, on Windows, when the link points into another person's user folder.
- A link that ends with a hidden character, or that names a drive the way some PDF programs write it (/C/Users/...), opens its file; a link to a named spot in another PDF opens that PDF at that spot.

## 1.10.1 (es)

**Correcciones**
- Vínculos a otros archivos, como en un índice de planos: cuando el archivo vinculado no está donde dice el vínculo (el índice se creó en el equipo de otra persona, o las carpetas se movieron o se sincronizan en otro lugar), KanzonasPDF lo busca desde la carpeta del documento que está leyendo y lo abre; la barra de estado indica qué archivo abrió. Si no lo encuentra, el mensaje lo dice y, en Windows, indica cuándo el vínculo apunta a la carpeta de usuario de otra persona.
- Un vínculo que termina con un carácter oculto, o que nombra una unidad como la escriben algunos programas de PDF (/C/Users/...), abre su archivo; un vínculo a un lugar con nombre de otro PDF abre ese PDF en ese lugar.

## 1.10

**New**
- Smart forms: fields can add up, multiply, average or follow a formula (like Price * Qty + Shipping) and work themselves out as you fill in the form, saved the way Acrobat saves them (KanzonasPDF never runs scripts from the file). Fields can show money, percents, dates, ZIP codes and phone numbers and refuse values that don't fit; in a percent field, 25 means 25%. Forms > Detect form fields makes fields on a flat or scanned form, and Field properties, Set tab order and Check required fields are on the ribbon's Forms tab.
- Comments review: reply to comments and to replies, set a review status (Accepted, Rejected, Cancelled, Completed), export and import comments as XFDF or FDF files (Acrobat's comment files import with their text and formatting), and Summarize comments into a PDF.
- Accessibility (Document > Accessibility): check a PDF against PDF/UA, the standard for screen readers, and fix what it finds. Auto-tag gives an untagged document its tags; describe pictures, set the reading order, the title and language, and more. Editing a tagged document keeps its tags right.
- Batch processing (Tools > Batch processing...): the same steps on many PDFs at once (OCR, PDF/A, Bates numbers, watermarks, flattening, redaction, smaller files), into a Processed folder; your originals stay as they were. Search & redact in a batch says, for each file, what was removed and where.
- Bookmarks made automatically from a document's headings, a tagged PDF's headings or a drawing set's sheet numbers and titles; Insert table of contents (each line a link, updated in place); a Bookmarks panel that sorts, styles, expands and collapses, and Ctrl+B to bookmark what you're looking at.
- Reading comfort, on a new Reading tab: Full screen, Presentation (F5), two pages side by side, Reading view, Read aloud with your computer's own voices, and Auto scroll.

**Fixed**
- Redaction: a mark covering only part of a tagged piece of text left a hidden copy of those words in the file; redacting a tagged document also removes the descriptions of what you redacted; a form field removed by redaction leaves nothing of itself, and totals that used it are worked out again without it.
- Deleting a form field or its page leaves nothing of the field in the file.
- Combine files keeps where each bookmark goes and its style; after Replace pages a bookmark still goes to its spot on the new drawing.
- The downloads are smaller: the video libraries Read aloud doesn't need are left out.
- Security: a PDF or an imported comment file can no longer make an image stamp bring a picture from elsewhere on your computer or network into the document; image stamps come only from your stamp library.
- Redaction: text tagged inside a drawing of its own, an export made before Search & redact in a batch, and a Presentation still showing the old page could all keep redacted words; they no longer do.
- Batch processing never writes outside the chosen output folder, even through a link placed there, and never changes your originals; a skipped or failed file is left out of the combined PDF, so Bates numbers are never used twice.
- Files with damaged tags, bookmarks nested very deep, impossible comment positions, huge stamps or formulas, or lists that loop no longer hang or stop with an error. Importing thousands of comments is fast, and so is editing a large tagged document.
- Cutting a comment and pasting it elsewhere keeps its replies and statuses; a sticky note added to an accessible document keeps it accessible; a table of contents inserted in a tagged PDF is tagged as one.

## 1.10 (es)

**Novedades**
- Formularios inteligentes: los campos pueden sumar, multiplicar, promediar o seguir una fórmula (como Precio * Cant + Envío) y se calculan solos mientras rellena el formulario, guardados como los guarda Acrobat (KanzonasPDF nunca ejecuta scripts del archivo). Los campos pueden mostrar dinero, porcentajes, fechas, códigos postales y teléfonos y rechazan valores que no encajan; en un campo de porcentaje, 25 significa 25%. Formularios > Detectar campos de formulario crea campos en un formulario plano o escaneado, y Propiedades del campo, Establecer el orden de tabulación y Comprobar campos obligatorios están en la pestaña Formularios de la cinta.
- Revisión de comentarios: responda a comentarios y a respuestas, establezca un estado de revisión (Aceptado, Rechazado, Cancelado, Completado), exporte e importe comentarios como archivos XFDF o FDF (los archivos de comentarios de Acrobat se importan con su texto y su formato) y resuma los comentarios en un PDF.
- Accesibilidad (Documento > Accesibilidad): compruebe un PDF según PDF/UA, el estándar para lectores de pantalla, y corrija lo que encuentre. Etiquetar automáticamente da etiquetas a un documento sin ellas; describa las imágenes, fije el orden de lectura, el título y el idioma, y más. Editar un documento etiquetado mantiene bien sus etiquetas.
- Procesamiento por lotes (Herramientas > Procesamiento por lotes...): los mismos pasos en muchos PDF a la vez (OCR, PDF/A, números Bates, marcas de agua, acoplar, censurar, archivos más pequeños), en una carpeta Procesados; sus originales quedan como estaban. Buscar y censurar en un lote dice, de cada archivo, qué se quitó y de dónde.
- Marcadores creados automáticamente a partir de los títulos de un documento, de los títulos de un PDF etiquetado o de los números y títulos de los planos de un juego; Insertar tabla de contenido (cada línea un vínculo, actualizada en su lugar); un panel Marcadores que ordena, da estilo, expande y contrae, y Ctrl+B para marcar lo que está viendo.
- Comodidad de lectura, en una nueva pestaña Lectura: Pantalla completa, Presentación (F5), dos páginas lado a lado, Vista de lectura, Leer en voz alta con las voces de su computadora y Desplazamiento automático.

**Correcciones**
- Censura: una marca que cubría solo parte de un texto etiquetado dejaba en el archivo una copia oculta de esas palabras; al censurar un documento etiquetado también se quitan las descripciones de lo censurado; un campo de formulario quitado al censurar no deja nada de sí, y los totales que lo usaban se calculan de nuevo sin él.
- Eliminar un campo de formulario o su página no deja nada del campo en el archivo.
- Combinar archivos conserva a qué lugar lleva cada marcador y su estilo; después de Reemplazar páginas, un marcador sigue llevando a su lugar en el dibujo nuevo.
- Las descargas son más pequeñas: se dejan fuera las bibliotecas de video que Leer en voz alta no necesita.
- Seguridad: un PDF o un archivo de comentarios importado ya no puede hacer que un sello de imagen traiga al documento una imagen de otro lugar de su computadora o de la red; los sellos de imagen salen solo de su biblioteca de sellos.
- Censura: el texto etiquetado dentro de un dibujo propio, una exportación hecha antes de Buscar y censurar en un lote y una Presentación que seguía mostrando la página anterior podían conservar palabras censuradas; ya no.
- El procesamiento por lotes nunca escribe fuera de la carpeta de salida elegida, ni siquiera a través de un vínculo puesto allí, y nunca cambia sus originales; un archivo omitido o con error queda fuera del PDF combinado, así que los números Bates nunca se repiten.
- Los archivos con etiquetas dañadas, marcadores anidados a mucha profundidad, posiciones imposibles en comentarios, sellos o fórmulas enormes, o listas que se repiten ya no se bloquean ni se detienen con un error. Importar miles de comentarios es rápido, y también editar un documento etiquetado grande.
- Cortar un comentario y pegarlo en otro lugar conserva sus respuestas y estados; una nota adhesiva agregada a un documento accesible lo mantiene accesible; una tabla de contenido insertada en un PDF etiquetado se etiqueta como tal.

## 1.9.1

**New**
- Text you add is remembered as one piece. Click any line of it with Edit text and the whole text opens, with its line breaks and each word's style, and goes back exactly where it was.
- With Edit objects, copy, cut, paste and duplicate the page's own text (Ctrl+C, Ctrl+X, Ctrl+V, Ctrl+D), keeping its fonts and styles, on any page or into another document. Duplicate copies pictures and shapes too, and CAD Copy now copies text.
- With Edit objects, copy or cut the page's own pictures and shapes (with any text) and paste them on another page or into another document. They look exactly the same and can still be edited there.
- In CAD mode, Move and Copy work across pages: click the base point, then where it goes on any page. You can also drag a selection onto another page.

**Fixed**
- While you edit text, Bold, Italic and Font size in Properties change the words you selected, and they stay selected (before, clicking Bold there lost the selection and did nothing). With nothing selected, they change all the text in the box, and Properties shows the style of the selected words.
- The small style bar above the text being edited is easy to read, and shows which styles the selected words have.
- The box you type in is no bigger than the text: Add text's box is as wide as what you type, and text too small to read at your zoom (a drawing zoomed out) is typed enlarged just below its spot, with a true-size preview showing exactly where it goes.
- Printed lines are no longer faint: thin lines in drawings print solid and at least 0.15 pt wide (Dark thin lines in the Print window, on unless you turn it off).

## 1.9.1 (es)

**Novedades**
- El texto que agrega se recuerda como una sola pieza. Haga clic en cualquiera de sus líneas con Editar texto y se abre entero, con sus saltos de línea y el estilo de cada palabra, y vuelve exactamente a su lugar.
- Con Editar objetos, copie, corte, pegue y duplique el texto propio de la página (Ctrl+C, Ctrl+X, Ctrl+V, Ctrl+D) con sus fuentes y estilos, en cualquier página o en otro documento. Duplicar también copia imágenes y formas, y Copiar de CAD ahora copia el texto.
- Con Editar objetos, copie o corte las imágenes y formas propias de la página (con el texto que haya) y péguelas en otra página o en otro documento. Se ven exactamente igual y se siguen pudiendo editar allí.
- En el modo CAD, Mover y Copiar funcionan entre páginas: haga clic en el punto base y luego donde va, en cualquier página. También puede arrastrar una selección a otra página.

**Correcciones**
- Mientras edita texto, la Negrita, la Cursiva y el Tamaño de fuente de Propiedades cambian las palabras que seleccionó, y siguen seleccionadas (antes, hacer clic allí en Negrita perdía la selección y no hacía nada). Sin nada seleccionado, cambian todo el texto del cuadro, y Propiedades muestra el estilo de las palabras seleccionadas.
- La pequeña barra de estilos sobre el texto que se edita se lee con facilidad y muestra qué estilos tienen las palabras seleccionadas.
- El cuadro donde escribe no es más grande que el texto: el cuadro de Agregar texto es tan ancho como lo que escribe, y el texto demasiado pequeño para leerse con su zoom (un plano visto entero) se escribe ampliado justo debajo de su lugar, con una vista previa a tamaño real que muestra exactamente dónde va.
- Las líneas impresas ya no salen tenues: las líneas finas de los planos se imprimen sólidas y con al menos 0,15 pt de grosor (Líneas finas oscuras en la ventana Imprimir, activado salvo que lo desactive).

## 1.9

**New**
- **Scan** (File > Scan...): scan straight into a PDF from a scanner, or a printer that scans, without installing its driver: most network printers (eSCL/AirScan and WSD), the scanners Windows knows, and SANE on Linux. Pages started on the printer's own panel can come in too, and a folder can be watched for scans.
- **Edit text keeps each word's style**, and you can make words **Bold**, *Italic*, Underline or Strikethrough, or change their color and size, in the line's own font. Add text does the same.
- **Dimension** markups: a measured line with extension lines and arrows.
- **Legend** markups: a list of the page's or document's markups (kind, color, count, totals) that keeps itself up to date as you add, change or delete markups.
- **Replace pages** (Pages tab): put in a new revision of a page or drawing and keep its markups, links and bookmarks; pages are matched by number or by sheet number.
- **Save as PDF/A...** and **Check PDF/A...** (File menu): an archival copy (PDF/A-2b), and a list of what keeps a file from being one.
- The page's scale shown large on the Measure tab and in the status bar (red when it isn't set), a notice the first time you measure an unscaled page, and an on-screen **Scale bar**.
- **KanzonasPDF for Mac** with Apple silicon (M1 or newer), macOS 14.4 or newer.

**Fixed**
- Redaction leaves nothing behind: Search & redact also finds the text in hidden layers, in parts of a page that were cropped away, and in other places in the file (layer names, web addresses, form data), and offers to remove it there. Applying redactions no longer leaves copies in a note's formatted text, hidden form fields, XFA form data, page thumbnails, the hidden text that describes the redacted words, review threads, or the private data some programs (like Illustrator) keep. Legends are redrawn without the redacted words, and a signed copy made after redacting no longer contains what was removed.
- Edit text: words a page hides (a scan's recognized text) stay hidden when you edit, move or replace text near them; words made larger no longer overlap the line above; editing a paragraph no longer moves words to the next line. Hebrew and Arabic are left as they are, with a message, instead of being written backwards.
- A picture dropped near the middle of the page snaps to the center even with Snap to objects on.
- Replace pages keeps markups the right way up on a turned sheet, and text sizes, line widths and measurements follow a sheet of another size.
- Markups keep their subject (their name in legends) when restyled, copied or measured again; Set scale no longer deletes replies to measurements; colors from other programs (gray, CMYK) read correctly.
- Scanning: a page cut short by a dropped connection is reported instead of kept as half a page, Cancel stops a page that is still arriving, files in a watched folder are taken only once they're complete, and a scanned PDF brings only its pages (no links, fields or comments).
- Save as PDF/A also fixes pictures stored inside the page content; Check PDF/A reports a few more things PDF/A doesn't allow. Saves that tidy the file (Compress, Save as PDF/A, Combine files) can no longer lose a page's drawing.
- Pages look exactly like the file opened afresh after adding or undoing a highlight, or moving a picture stamp partly off the page.
- Edit objects: deleting or moving shapes and text together on a page with redaction marks not applied yet no longer makes Redo unavailable.
- Scanning on a Mac no longer waits about half a minute before looking for scanners, and the Mac asks once to let KanzonasPDF find devices on your network. On Windows, Cancel stops a page that is still arriving.
- Find no longer counts a word twice when part of it is in another size, and its count goes when the last document closes. The ribbon fits a 1366-pixel screen in Spanish too, and recognizing text (OCR) uses less memory.

## 1.9 (es)

**Novedades**
- **Escanear** (Archivo > Escanear...): escanee directamente a un PDF desde un escáner, o una impresora que escanea, sin instalar su controlador: la mayoría de las impresoras de red (eSCL/AirScan y WSD), los escáneres que Windows conoce y SANE en Linux. También pueden llegar las páginas iniciadas en el panel de la impresora, y se puede vigilar una carpeta de escaneos.
- **Editar texto conserva el estilo de cada palabra**, y puede poner palabras en **Negrita**, *Cursiva*, Subrayado o Tachado, o cambiar su color y tamaño, con la fuente de la propia línea. Agregar texto hace lo mismo.
- Marcas de **Cota**: una línea medida con líneas de extensión y flechas.
- Marcas de **Leyenda**: una lista de las marcas de la página o del documento (tipo, color, cantidad, totales) que se mantiene al día al agregar, cambiar o eliminar marcas.
- **Reemplazar páginas** (pestaña Páginas): ponga una nueva revisión de una página o un plano y conserve sus marcas, vínculos y marcadores; las páginas se emparejan por número o por número de hoja.
- **Guardar como PDF/A...** y **Revisar PDF/A...** (menú Archivo): una copia de archivo (PDF/A-2b), y una lista de lo que impide que un archivo lo sea.
- La escala de la página se muestra en grande en la pestaña Medir y en la barra de estado (en rojo cuando no está establecida), un aviso la primera vez que mide en una página sin escala, y una **Barra de escala** en pantalla.
- **KanzonasPDF para Mac** con Apple silicon (M1 o posterior), macOS 14.4 o posterior.

**Correcciones**
- La censura no deja nada atrás: Buscar y censurar también encuentra el texto en capas ocultas, en las partes recortadas de una página y en otros lugares del archivo (nombres de capas, direcciones web, datos de formularios), y ofrece quitarlo de allí. Aplicar censuras ya no deja copias en el texto con formato de una nota, campos de formulario ocultos, datos de formularios XFA, miniaturas de página, el texto oculto que describe las palabras censuradas, hilos de revisión ni los datos privados que algunos programas (como Illustrator) guardan. Las leyendas se vuelven a dibujar sin las palabras censuradas, y una copia firmada hecha después de censurar ya no contiene lo que se quitó.
- Editar texto: las palabras que la página oculta (el texto reconocido de un escaneo) siguen ocultas al editar, mover o reemplazar el texto de su alrededor; las palabras agrandadas ya no se montan sobre la línea de arriba; editar un párrafo ya no pasa palabras a la línea siguiente. El hebreo y el árabe se dejan como están, con un mensaje, en lugar de escribirse al revés.
- Una imagen soltada cerca del centro de la página se ajusta al centro aunque Ajustar a objetos esté activado.
- Reemplazar páginas deja las marcas derechas en una hoja girada, y los tamaños de texto, los grosores de línea y las mediciones siguen a una hoja de otro tamaño.
- Las marcas conservan su asunto (su nombre en las leyendas) al cambiarles el estilo, copiarlas o volver a medirlas; Establecer escala ya no borra las respuestas a las mediciones; los colores de otros programas (gris, CMYK) se leen bien.
- Escanear: una página cortada por una conexión caída se avisa en lugar de guardarse a medias, Cancelar detiene una página que todavía está llegando, los archivos de una carpeta vigilada se toman solo cuando están completos, y un PDF escaneado trae solo sus páginas (sin vínculos, campos ni comentarios).
- Guardar como PDF/A también corrige las imágenes guardadas dentro del contenido de la página; Revisar PDF/A indica algunas cosas más que PDF/A no permite. Los guardados que ordenan el archivo (Comprimir, Guardar como PDF/A, Combinar archivos) ya no pueden perder el dibujo de una página.
- Las páginas se ven exactamente como el archivo abierto de nuevo después de agregar o deshacer un resaltado, o de mover un sello con imagen en parte fuera de la página.
- Editar objetos: eliminar o mover formas y texto a la vez en una página con marcas de censura sin aplicar ya no deja Rehacer sin efecto.
- Escanear en un Mac ya no espera cerca de medio minuto antes de buscar escáneres, y el Mac pide una vez permitir que KanzonasPDF encuentre dispositivos en su red. En Windows, Cancelar detiene una página que todavía está llegando.
- Buscar ya no cuenta dos veces una palabra que tiene una parte en otro tamaño, y su recuento desaparece al cerrar el último documento. La cinta de opciones cabe en una pantalla de 1366 píxeles también en español, y el reconocimiento de texto (OCR) usa menos memoria.

## 1.8.3

**Fixed**
- Redo is available right after an Undo. Undoing some changes (inserting a page, for example) left Redo grayed out, and Ctrl+Y did nothing, until something else happened in the window.
- An edited markup stays in its place in the stack: after you changed a markup's text, color or size, it was drawn on top of the markups above it until the file was saved.
- Duplicating, copying or extracting pages (and Capture area) no longer changes the document you copy from. Sticky notes on those pages lost the link to their pop-up, and the next Undo didn't bring the document back exactly as it was.
- A page duplicated twice no longer shares its markups with its copy after Apply redactions or Copy pages: moving or deleting a markup on one page moved or deleted it on the other too.
- Behind the scenes: a new test drives thousands of random edits, undos, redos and saves through the app and checks the document after every step, to catch bugs like these before a release.

## 1.8.3 (es)

**Correcciones**
- Rehacer está disponible justo después de Deshacer. Al deshacer algunos cambios (insertar una página, por ejemplo), Rehacer quedaba atenuado y Ctrl+Y no hacía nada hasta que ocurría otra cosa en la ventana.
- Una marca editada se queda en su lugar en la pila: después de cambiar el texto, el color o el tamaño de una marca, se dibujaba encima de las marcas que estaban sobre ella hasta guardar el archivo.
- Duplicar, copiar o extraer páginas (y Capturar área) ya no cambia el documento del que se copia. Las notas adhesivas de esas páginas perdían el vínculo con su ventana emergente, y el siguiente Deshacer no devolvía el documento exactamente como estaba.
- Una página duplicada dos veces ya no comparte sus marcas con su copia después de Aplicar censuras o Copiar páginas: mover o eliminar una marca en una página la movía o eliminaba también en la otra.
- Internamente: una nueva prueba realiza miles de ediciones, deshacer, rehacer y guardados al azar en la aplicación y revisa el documento después de cada paso, para detectar errores como estos antes de publicar una versión.

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
