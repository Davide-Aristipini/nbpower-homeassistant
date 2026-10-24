# Cattura FRITZ!Box, solo se necessaria

L'APK ufficiale ha già consentito di identificare le API. La prima operazione
utile è ora il login interattivo con `scripts/probe_cloud.py`; un PCAP non è
necessario per quel tentativo. Se occorre esaminare traffico/disconnessioni:

1. Dal PC apri `http://fritz.box/support.lua` e accedi normalmente al router.
2. Cerca **Cattura pacchetti / Packet captures / Paketmitschnitt**. A seconda
   della lingua e versione FRITZ!OS, la pagina dedicata è raggiungibile da
   `http://fritz.box/capture.lua` oppure dal collegamento della pagina supporto.
3. Seleziona l'interfaccia WLAN a cui è associata la colonnina (2,4 GHz o
   interfaccia del nodo Mesh effettivo). Un'acquisizione sulla sola WAN può
   nascondere gli IP privati per effetto NAT. Se la WLAN non mostra il traffico,
   acquisisci anche l'interfaccia LAN/bridge disponibile.
4. Avvia una cattura di circa 60–120 secondi. Sul telefono apri NBPower,
   visualizza la colonnina e attendi aggiornamenti dei valori. Non avviare o
   interrompere sessioni e non cambiare la corrente per questa cattura.
5. Ferma e salva il file in `nbpower-homeassistant/private/` (creala localmente),
   per esempio `private/nbpower-idle.pcap`. Quella cartella è esclusa da Git.
6. Comunica il percorso locale del file, così può essere analizzato senza
   pubblicarlo. Un PCAP può includere dati di altri dispositivi e credenziali
   in protocolli non cifrati: il report estrarrà soltanto metadati di rete.

Controlla l'indirizzo della colonnina nel router. Il MAC Wi-Fi potrebbe essere
diverso dall'identificativo nel nome dell'app. Il PC Ethernet non
vede normalmente il traffico unicast Wi-Fi→Internet senza questa cattura sul
router. Non sono state eseguite intercettazioni ARP o modifiche del gateway.

## Analisi predisposta

Tshark non è risultato installato nel percorso standard o nel PATH. Se si rende
necessario, installare Wireshark/Tshark richiederà prima concordare l'installazione;
per leggere un file già acquisito non serve installare un driver di cattura.

```powershell
python scripts/analyze_capture.py "private/nbpower-idle.pcap" --ip IP_PRIVATO_COLONNINA
```

Lo script usa `tshark -n -r`, limita all'indirizzo indicato con `--ip` ed estrae
solo indirizzi/porte IP, query DNS e TLS SNI. Non stampa URL HTTP, cookie,
messaggi MQTT, password o token. È stato verificato sintatticamente, ma non
eseguito su una cattura reale, perché non ne è ancora disponibile una.

Il PCAP cifrato può identificare server e protocolli, ma non da solo i payload
HTTPS. La disponibilità di SNI e DNS dipende anche da TLS e dalla cache DNS.
