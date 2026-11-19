# Cómo reservar su catálogo frente al entrenamiento de IA en 10 minutos

Guía para editoriales que usan TDM Seal 1.0. No hace falta saber programar.

## Antes de empezar (1 minuto)

Tenga a mano:

- el nombre de la editorial, su sitio web y un **correo de derechos** donde
  recibir solicitudes de licencia;
- la carpeta con los **PDF o EPUB finales** del catálogo. TDM Seal nunca
  modifica los originales: crea una copia `_TDM` junto a cada archivo.

Una idea clave: la reserva **no es un "no" definitivo**. Es una declaración,
legible por máquinas y por personas, de que el uso para minería de textos y
entrenamiento de IA requiere licencia. Lo que se busca es que quien quiera
usar sus libros le escriba.

## 1. Datos de la editorial (1 minuto)

Abra **TDM Seal** (icono del Escritorio). En la pestaña **Sellar**:

1. Escriba nombre, sigla, sitio web y correo de derechos.
2. Deje marcada la opción **Reservados (recomendado)**.
3. En **URL de la política** escriba dónde publicará su política, por
   ejemplo `https://suseditorial.ejemplo/tdm/policies/1`. Puede publicarla
   después; lo importante es decidir la dirección ahora.
4. Pulse **Guardar como valores por defecto**.

## 2. La política de licencia (2 minutos)

En la pestaña **Política**:

1. Elija las condiciones para **investigación** (por ejemplo, "Con
   autorización previa") y para **otros fines**, comerciales y de IA
   incluidos (por ejemplo, "Con autorización y compensación económica").
2. Revise las **preferencias de IA**. Las recomendadas son: entrenar
   modelos, *reservado*; usar como entrada de IA, *reservado*; búsqueda,
   *permitido*, para que sus libros sigan apareciendo en los buscadores.
3. Mire la **vista previa**: es la página que verá quien quiera licenciar.
4. Pulse **Generar archivos de política…** y elija una carpeta. Obtendrá
   `policy.html`, `policy.jsonld` y `tdmrep.json`.

## 3. Sellar el catálogo (3 minutos)

De vuelta en **Sellar**:

1. **Seleccionar carpeta…** (marque *Incluir subcarpetas* si hace falta).
   TDM Seal audita cada archivo: formato, firma, cifrado o DRM, y si ya tenía
   reserva.
2. Deje marcado **Calcular ISCC**: es la huella del contenido, que permite
   reconocer la obra aunque cambie de nombre o de formato.
3. El **aviso visible** está desactivado. Actívelo solo si quiere añadir
   una página final con la reserva en lenguaje claro; no toca las páginas
   existentes.
4. Pulse **Aplicar TDM**. Los firmados, cifrados o con DRM se omiten sin
   tocarlos. Junto a cada copia `_TDM` queda un reporte `.report.json`.

**Distribuya las copias `_TDM`**, no los originales.

## 4. El sitio web (2 minutos más lo que tarde su webmaster)

En **Sitio web**, pulse **Generar archivos del sitio…** y elija una carpeta.
Entregue esa carpeta a quien administra su web, con su `LEEME.txt`:

- `/.well-known/tdmrep.json` va en la raíz del sitio;
- `servidor/apache.conf` o `servidor/nginx.conf` añaden las cabeceras HTTP;
- `servidor/robots-content-usage.txt` son líneas para **añadir** al
  robots.txt, no para sustituirlo;
- publique también `policy.html` y `policy.jsonld` en la URL que eligió en
  el paso 1.

## 5. El manifiesto del catálogo (1 minuto)

En **Catálogo**, pulse **Generar manifiesto…** y guárdelo como `.csv` (se
abre en Excel) o `.json`. Tiene una fila por obra con su ISCC, ISBN, hashes,
reserva y política. Sirve para:

- cargarlo en un registro ISCC o entregarlo a su sociedad de gestión;
- negociar licencias en bloque con otras editoriales o con empresas de IA.

## Y después

- Cada libro nuevo: séllelo antes de distribuirlo y antes de firmarlo
  digitalmente (un PDF firmado no se puede sellar sin invalidar la firma).
- Conteste las solicitudes que lleguen al correo de derechos: para eso
  existe la reserva.
- TDM Seal no sustituye la asesoría jurídica ni la gestión colectiva: es la
  parte técnica para que la reserva quede expresada en todos los sitios
  donde una máquina puede leerla.
