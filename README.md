# Coppa dei 5 Re

App iOS SwiftUI per iPhone 12 e iOS 18.4. Include dashboard, calendario, inserimento risultati, classifica locale aggiornata immediatamente, pronostici, giocatori e playoff.

## Build cloud
GitHub Actions usa un runner macOS con Xcode per creare un IPA non firmato. Apri Actions e avvia il workflow `Build Coppa5Re unsigned IPA`, oppure esegui un push sul branch main.

## Installazione
Scarica l'artifact `Coppa5Re-unsigned-IPA` dalla run completata. Importa l'IPA in Sideloadly su Windows e firmalo con il tuo Apple Account. Non inserire password Apple o certificati nel repository o in chat.

I risultati sono salvati localmente sul telefono; non è prevista sincronizzazione multi-dispositivo.


## Versione Windows desktop

Nel percorso `windows_app/` è disponibile anche la versione desktop nativa per Windows: due scacchiere live, mosse legali, calendario, risultati, classifica, penalità, quote simulate e modalità spettatore.

Per ottenere il file `.exe`, apri la scheda [Actions](https://github.com/red04yes-cyber/Coppa5Re-iOS/actions/workflows/build-windows.yml) e scarica l'artifact `Coppa5Re-Windows-EXE` dalla build completata. L'app salva i dati in locale sul PC e può funzionare offline.
