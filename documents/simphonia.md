# simphonia

- Module principal de l'application
- développé en python
- repose sur le principe publich/subscribe
- mise en place d'un système de event-bus simple mais multi-bus

## bus

### bus: system

bus destiné à recevoir les commandes systèmes de bases comme, par exemple, la commande /help (retourne la liste de toutes les instructions connues du bus ainsi que le description associées).

chaque commande dois pouvoir s'enregistrer auprès du bus au démarrage du serveur en utilisant le principe des annotations pour chaque commande

une commande est, à minima, composée d'un code unique, d'une description, d'une fonction callback qui sera appelée par le bus