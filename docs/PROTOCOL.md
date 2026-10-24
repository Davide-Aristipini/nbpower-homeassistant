# Protocollo NBPower: evidenze e implementazione iniziale

## Provenienza

Fonte primaria: `https://c.echgr.com/nbpower.apk`, app 2.0.16 (20016), collegata
dal sito NBPower. SHA256 nel rapporto e in `reports/apk.json`.
Bundle: `assets/apps/__UNI__BA41F23/www/app-service.js`.
Gli offset qui indicati sono indici nel testo Unicode estratto, non indirizzi
di firmware. `scripts/index_source.py` crea estratti consultabili in `research/`.

## Trasporto HTTP e discovery

Configurazione modulo `1f29`, intorno all'offset 93.650:
`requestDomain=https://g.echgr.com/`, `businessID=2`.
Modulo `6b0f` (`components/post.vue`), offset 539.000–550.000:
fallback presente nel codice `https://c.echgr.com/`.

1. POST JSON `https://g.echgr.com/api/getUserServer`, con `accesstoken` se presente.
2. Risposta attesa confermata live su `c.echgr.com`:
   `{"code":0,"data":{"server":"g.echgr.com","address":"…"}}`.
3. POST JSON `https://<server>/api/<azione>`, timeout app 12 secondi.
   Il client usa 15 secondi e un solo fallback di bootstrap su `c.echgr.com`.

Il client accetta destinazioni HTTPS sotto `echgr.com`. Altri domini risultano
nella risposta pubblica, ma non saranno destinatari di credenziali finché non
saranno necessari e verificati per questo account.

## Firma

`post.vue`, offset circa 542.496:

- Include metadati `_platform`, `_system`, `_brand`, `_model`, `_businessID`,
  `_locale`, `_version`, `_versionCode`. Il client usa metadati espliciti propri
  e versione dell'APK; non impersona un telefono specifico.
- Aggiunge `_proj`, `_sig_ts` (epoch secondi) e `accesstoken`, se presente.
- Scarta i valori null/undefined e la vecchia `sig`.
- Ordina le chiavi lessicograficamente; converte oggetti/array con JSON.stringify.
- Applica encodeURIComponent ai valori e concatena `key=value` con `&`.
- Prefisso/progetto sono costanti pubbliche offuscate dell'app (array numerici
  decodificati sottraendo l'indice), non credenziali dell'account.
- Firma `MD5(prefisso + "&" + canonico).hexdigest()[8:24]`.
  Il modulo MD5 `2478` conferma la variante middle-16 all'offset 98.247.

`getQRDomains` ha accettato il payload Python firmato su c.echgr.com e g.echgr.com.
Un singolo controllo negativo sullo stesso endpoint c.echgr.com, alterando
soltanto la firma, ha restituito `code=999`, mentre il payload valido riceve 0.
Il riferimento Node confronta booleani, JSON annidato, email con `+` e timestamp fisso.
Questa accettazione non convalida ancora le richieste autenticate.

## Autenticazione

Pagina login, offset 511.535–513.290:

| Azione | Parametri evidenziati | Risposta usata dall'app |
|---|---|---|
| getTelCode | mail, code | code 0 per successo |
| telLoginByCode | mail, code=OTP, address se disponibile | accesstoken, refreshtoken |
| refreshtoken | refreshtoken | nuovi token |

Il form inizializza `code="1234"` per getTelCode e contiene un riferimento a
`api/imgCode`. L'eventuale necessità di captcha va verificata sul server reale
prima di dichiarare completo il flusso OTP.

`code=10000` indica sessione da rinnovare; l'app usa il refresh token oppure
ritorna al login. Il client limita il rinnovo a un tentativo per richiesta e
serializza rinnovi concorrenti. I token sono dati top-level della risposta;
questo è ricavato dal codice, non verificato con un account reale.

## Elenco e stato

`getBindedChargers`, offset 517.371, senza parametri di selezione:
risposta `.list`, elementi con `.imei`, `.mac`, `.id` nel codice delle pagine.
Il client richiede che la lista contenga IMEI e ne consente la selezione solo
dopo login. Non assume che l'IMEI coincida con nome BLE o MAC Wi-Fi.

Modulo `e27e`, `lib/netMode.js`, offset circa 1.332.000:

1. `getChargerServer`, `{imei}` → `.server` top-level.
2. Su quel server: `getNBPNetStatus`, `{imei}` → `.heartDB.data`, `.activeTime`,
   opzionali `.imei`, `.charger`, `.order`.
3. L'app apre `wss://<server>?imei=<imei>`; ogni messaggio è una stringa di byte
   numerici separati da virgole. L'implementazione iniziale usa solo polling
   autenticato; il push richiede verifica della sessione e dell'effettivo flusso.

## Decodifica heartDB

Fonte `heartDBAnalysis`, offset circa 1.337.000, e `calcMeterDB` a 550.012.
Formato:

```text
[lunghezza_header, ...header di rete..., lunghezza_record, comando, req_id, ...payload, ...]
```

Il primo record inizia a `data[0]+1`. Ogni record occupa `lunghezza_record+1`
byte; il payload inizia tre byte dopo l'inizio del record e termina al confine
successivo. Byte e lunghezze sono verificati rigorosamente dal parser.

- CMD 1: payload[0] firmware; [1] modello; [2] numero/indicazione contatori.
- CMD 49: [0] stato; [1] temperatura 1; [2] temperatura 3; [4] temperatura 2;
  [15] temperatura 4, se presente. Temperatura = byte−40, tranne 255 sconosciuto.
  [5] codice errore; [6:8] informazione errore; [16] fasi utilizzate per fw >27.
- Stato: 0 scollegata, 1 standby, 2 pianificata, 3 ricarica, 4 potenza ridotta,
  5 raffreddamento, 255 aggiornamento.
- CMD 8, firmware >27: `V=u16be(0)/10`, `A=u16be(2)/10`,
  `P_attiva=u16be(4)`, `kWh_sessione=u16be(6)/100`.
- L'app calcola anche `V*A`, diverso dalla potenza attiva. Il sensore W usa
  P_attiva. Il valore 4.848,3 riportato nello screenshot potrebbe essere V*A:
  225,5×21,5=4.848,25, ma serve una lettura reale per confermarlo.
- Firmware <=27: formato legacy e calibrazione impulsi, presenti nel parser.
- In multifase l'app somma potenza attiva ed energia dei CMD 8,13,14;
  il client richiede tutti i record per non sottostimare i valori. Tensione e
  corrente esposte rimangono della prima fase.
- CMD 12 contiene un contatore esterno opzionale: non esposto finché non è
  verificato che appartenga all'energia della colonnina.

`activeTime` viene passato a `new Date()` dall'app. Il client ammette millisecondi
epoch o ISO con fuso esplicito e rifiuta dati oltre 120 secondi o nel futuro oltre
60 secondi. Il formato e il periodo reale vanno verificati sul primo login.

## Comandi opt-in in v0.2

`ctrlNBP`, payload `{imei, db:[comando, req_id, ...parametri]}`, restituisce
`.res.data`; l'app scarta i primi tre byte per ottenere la risposta comando.
Le letture reali CMD 1 e 47 hanno confermato il formato di risposta e mostrato
che il cloud sostituisce il req_id. Il primo byte coincide con la lunghezza
totale meno uno; il secondo identifica il comando. Una colonnina letta riporta
firmware 45, device_num 15, un contatore, massimo hardware 32 A e run_mode 1.
Questo massimo hardware non sostituisce il limite della linea o del cavo.

Pagina dispositivo `startCharge`, offset 324.321:

- CMD 66 per challenge, dopo il normale controllo della password dispositivo.
- CMD 67 per avvio/modifica/arresto; payload con challenge, minuti big-endian,
  ritardo big-endian e PWM corrente.
- Lo stop nell'app richiama `startCharge(0)`. **Non è confermata l'ipotesi di
  usare heartbeat con parametro zero per fermare**: l'APK mostra un altro percorso.
- La modifica degli ampere durante la ricarica passa dal rinnovo dei parametri
  della sessione, quindi non va trattata come una semplice proprietà indipendente.
- `pay(true)` / `startCharge(..., true)` usa un marcatore dedicato per modificare
  una sessione già attiva. Questo percorso dell'app è riprodotto solo dopo
  l'adozione esplicita della sessione; gli avvii da fermo usano CMD 66.
- Avvio, variazione 6/8 A e stop sono stati verificati sulla variante AC
  monofase firmware 45 / device_num 15. Risposte stop corte e timeout non
  equivalgono a un rifiuto: il risultato viene verificato con telemetria fresca,
  senza reinviare alla cieca il comando.
- CMD 8 letto direttamente risolve il ritardo osservato fra nuovo PWM e cache
  cloud del contatore. La lettura più recente non viene sovrascritta subito
  dal precedente valore della cache.
- CMD 48 è stato usato una volta, con autorizzazione, per abbassare il solo
  byte del massimo di corrente; rilettura integrale dei parametri invariati.
  L'integrazione non cambia automaticamente le protezioni al caricamento.

## Limiti delle evidenze

Il proprietario ha eseguito una sessione reale con il client: OTP, login, elenco,
discovery server e decodifica della telemetria sono riusciti per il dispositivo
indicato. Sono disponibili i valori normalizzati forniti dal proprietario, non
una cattura grezza dell'heartbeat. Letture e controlli sono ora verificati
sulla sola variante monofase descritta. Il rinnovo reale su scadenza resta
da convalidare sul campo; concorrenza e limiti sono testati automaticamente.
Le fixture dei test sono
**sintetiche**, costruite usando il formato e i valori indicativi dell'utente.
OCPP, MQTT e UDP locale rimangono non confermati per questo modello.
