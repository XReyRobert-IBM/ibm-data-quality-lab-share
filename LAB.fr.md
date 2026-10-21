# Reproduire le lab sur IBM Cloud

Ce guide reproduit **demo-v2**, avec 200 clients synthétiques et vingt exigences. L’objectif est de proposer un contrôle SQL avec Granite, appliquer des définitions natives réutilisables, conserver les résultats, corriger les données puis relancer le même job.

Le parcours de référence a été validé les 15 et 16 octobre 2026. Les noms de colonnes et de définitions sont à conserver pour la reproduction ; les schémas et identifiants d’actifs sont propres à votre compte.

Avec Google Chrome, Python 3.9 ou ultérieur et un accès au dépôt, récupérer les fichiers :

```sh
gh repo clone XReyRobert-IBM/ibm-data-quality-lab-share
cd ibm-data-quality-lab-share
mkdir -p local
```

## 1. Préparer les ressources gratuites

Dans IBM Cloud, ouvrir le catalogue et vérifier les offres affichées avant de créer les ressources suivantes :

| Ressource | Usage | Offre observée dans le lab |
|---|---|---|
| watsonx.data intelligence | Définitions, règles et suivi | Trial, Francfort |
| watsonx.data integration | Exécution des jobs de qualité avec DataStage | Trial, Francfort |
| IBM Db2 | Source synthétique et audit | Lite, Londres |
| Stockage du projet | Actifs du projet | Stockage existant du projet sandbox |

Vérifier que les services sont **Active**. Ne sélectionner aucune offre payante si une offre gratuite n’est pas disponible. Le caractère gratuit des plans, les quotas et la disponibilité dépendent du compte et de la date ; l’observation du lab ne garantit pas un nouvel environnement gratuit.

Ouvrir watsonx dans la même région que les services intelligence et integration. Utiliser ou créer un projet avec un stockage fonctionnel. Le lab d’origine utilisait un projet sandbox existant ; une offre gratuite de stockage neuf n’a pas été validée dans un autre compte.

Pour vérifier le stockage, importer `rules/business-requirements-fr.txt` dans les actifs du projet, puis ouvrir son aperçu.

## 2. Créer la connexion Db2

Dans la ressource Db2, ouvrir **Service credentials → Create credential**. Utiliser un identifiant réservé au lab avec les droits nécessaires sur votre schéma. Le rôle disponible lors de l’essai était Manager ; le choix de droits de production est distinct du lab.

Dans les actifs du projet watsonx, créer une connexion **IBM Db2**, nommée par exemple `dq-demo-db2-connection`.

| Champ de connexion | Valeur des identifiants de service Db2 |
|---|---|
| Hostname | `connection.db2.hosts[0].hostname` |
| Port | `connection.db2.hosts[0].port` |
| Database | `connection.db2.database` |
| Username | `connection.db2.authentication.username` |
| Password | `connection.db2.authentication.password` |
| Certificat CA | `connection.db2.certificate.certificate_base64`, décodé en PEM |

Si nécessaire, placer uniquement le certificat base64 dans `local/db2-ca.base64`, puis le décoder localement :

```sh
openssl base64 -d -A -in local/db2-ca.base64 -out local/db2-ca.pem
```

Activer **Port is SSL-enabled**, renseigner le certificat PEM et conserver la vérification du nom d’hôte. Choisir les identifiants **Personal**, puis **Test connection**. Exiger **Test successful!**, enregistrer la connexion et vérifier sa présence dans les actifs.

Conserver les secrets dans les mécanismes d’identification IBM ; ne pas les inscrire dans les règles ou les fichiers versionnés du dépôt.

## 3. Préparer puis charger les 200 clients

Ouvrir Db2 **Manage → Go to UI → Run SQL**. Pour retrouver le schéma courant :

```sql
VALUES CURRENT SCHEMA;
```

Depuis la racine du dépôt, vérifier le jeu puis préparer les SQL avec votre schéma :

```sh
python3 scripts/validate_fixture.py
python3 scripts/prepare_lab.py --schema VOTRE_SCHEMA_DB2
```

Le contrôle local doit afficher **48 clients concernés, 55 violations et zéro après correction**. Il vérifie aussi les CSV, les valeurs nulles, les chaînes vides et les caractères Unicode ; il ne remplace pas l’exécution native IBM.

Dans un nouvel éditeur Db2, exécuter **une seule fois** `local/prepared/01_seed_clients.sql`, puis `local/prepared/00_schema_preflight.sql`. La table `VOTRE_SCHEMA_DB2.DQ_V2_CLIENTS_20261015` contient 200 lignes, dix colonnes métier et la clé `LAB_ROW_ID`. Choisir un schéma isolé si ces objets existent déjà ; le seed n’efface pas les tables existantes.

Créer ensuite la vue de référence avec `02_create_checks_view.sql`, consulter `03_reference_report.sql`, puis lancer `04_baseline_oracle.sql`, toujours depuis `local/prepared/`.

Les résultats attendus sont **55 couples règle/client en violation**, **48 clients distincts**, et **aucune ligne de différence** pour l’oracle. Le contrat complet se trouve dans [rules/contract.json](rules/contract.json) et les identifiants attendus dans [rules/expected-baseline.json](rules/expected-baseline.json).

## 4. Proposer une règle SQL avec Granite

Dans le projet : **Assets → Import assets → Connected data → votre connexion Db2 → votre schéma**. Importer `DQ_V2_CLIENTS_20261015` et, pour consulter la référence, `DQ_V2_CHECKS_20261015`.

Ouvrir **Manage → Data intelligence** et activer **Natural language queries**. Cette opération prépare les actifs du projet ; utiliser un projet dédié aux données synthétiques du lab et attendre la fin de la préparation.

Créer **New asset → Measure and monitor data quality**. Choisir **SQL query**, la connexion Db2 et la dimension **Completeness**, puis continuer vers l’éditeur SQL.

Dans **Reference assets**, sélectionner `DQ_V2_CLIENTS_20261015`. Copier le contenu de `local/prepared/granite-prompt.txt`, puis cliquer **Generate SQL**. Le modèle affiché lors du lab était `ibm/granite-4-h-small`.

Examiner la table, le schéma, les colonnes retournées et la condition. La règle recherche les noms nuls, vides ou constitués de blancs Unicode. `TRIM` seul ne couvre pas tout ce contrat ; la proposition doit traiter les espaces insécables et les séparateurs Unicode.

**Test query** doit afficher `LAB_ROW_ID integer` et `client_name varchar`. Lancer ensuite la proposition dans Db2 et vérifier les clients **3, 8, 12 et 190**. `local/prepared/09_ai_generated_name_query.sql` conserve la requête acceptée dans le lab comme référence. Le test de colonnes et la vérification des lignes métier sont deux contrôles complémentaires.

Cette rédaction concerne l’exigence BR_CLT_001. Le portefeuille suivant est construit avec les définitions natives ; il n’est pas présenté comme vingt règles automatiquement générées par l’IA.

## 5. Enregistrer les neuf définitions natives

Choisir **New asset → Define how to measure data quality**. Pour chaque entrée de [rules/native-definitions.json](rules/native-definitions.json), renseigner le **nom exact**, la dimension et l’expression ; valider puis enregistrer.

Les neuf logiques sont : présence, non-blanc, longueur, format ancré, types autorisés, catégories autorisées, pays autorisés, condition type/catégorie et unicité. Les noms exacts permettent au script de retrouver leurs nouveaux identifiants dans votre export d’audit.

Les expressions du langage de qualité utilisent des littéraux regex avec des antislashs doublés. Les motifs fournis comme paramètres utilisent les antislashs regex simples. Respecter le contenu décodé des chaînes JSON ; ne pas ajouter un niveau d’échappement supplémentaire lors de la saisie.

## 6. Appliquer les vingt exigences

Créer une règle nommée **DQ V2 - Client requirements portfolio**, en mode **Data quality definitions**. Ajouter les définitions et les associer aux colonnes et constantes de [rules/native-bindings-plan.json](rules/native-bindings-plan.json).

Vérifier notamment les points suivants :

- Le nom contient entre 2 et 100 caractères ; l’adresse au maximum 200.
- La même définition non-blanche est appliquée au nom et à l’adresse.
- Les cinq formats sont ancrés sur la chaîne entière et sensibles à la casse.
- La condition lie `clienttype` à `client_type` et `category` à `client_category`.
- Le téléphone est lié à `contact_phone`.
- Les vingt applications sont complètes et l’échantillonnage est désactivé.

Les populations diffèrent : les obligations de présence évaluent les 200 lignes ; les règles de validité excluent NULL mais évaluent les chaînes vides. La condition Individual → SME évalue 49 clients au départ, puis 50 après la correction du type d’un client. Les deux lignes d’un doublon d’identifiant doivent échouer.

## 7. Configurer une sortie d’audit persistante

Dans **Output**, activer la sortie externe avec votre connexion et votre schéma, dans une nouvelle table **DQ_V2_NATIVE_AUDIT_20261015**. Choisir **All records**, maximum **All**, méthode **Append** et import de la table générée comme actif. Laisser décochée la création uniquement en cas d’écart.

Conserver les onze colonnes source et ajouter les neuf attributs suivants :

| Libellé dans l’interface | Colonne attendue dans l’export |
|---|---|
| Data quality definition ID | `Data_quality_definition_ID` |
| Disambiguator | `Disambiguator` |
| Bound to column | `Bound_to_column` |
| Data quality definition | `Data_quality_definition` |
| Failing rules | `Failing_rules` |
| Passing rules | `Passing_rules` |
| Job run ID | `Job_run_ID` |
| Rule ID | `Rule_ID` |
| System time | `System_time` |

Le nom et l’identifiant de définition, la colonne liée et les identifiants d’exécution permettent d’interpréter l’audit sans reprendre les identifiants du projet d’origine. L’ajout conserve les observations avant et après correction.

## 8. Enregistrer et exécuter le job

Choisir **Create rule & define job**, nommer le job **DQ V2 - Clients - 20 requirements** et sélectionner l’environnement **Default DataStage PX S** si disponible. Conserver une exécution à la demande, sans planification ni notifications, puis vérifier les quotas avant **Create and run**.

Dans **Run history**, attendre le résultat métier **Successful** : 200 lignes testées, 152 conformes et 48 en écart. Examiner aussi l’état et les logs du job. Dans la référence, le statut technique était **Completed with warnings** ; l’acceptation repose sur le rapprochement des résultats, pas uniquement sur un libellé de succès.

## 9. Exporter et rapprocher votre première exécution

Sur l’exécution, choisir **Download → Download all** et enregistrer l’export complet dans `local/baseline.csv`. Ce fichier doit contenir les vingt colonnes d’audit définies à l’étape 7.

Préparer le rapport avec vos identifiants, puis rapprocher les ensembles exacts de clients :

```sh
python3 scripts/prepare_lab.py --schema VOTRE_SCHEMA_DB2 \
  --audit-csv local/baseline.csv

python3 scripts/verify_native_output.py local/baseline.csv \
  --state baseline --report local/baseline-reconciliation.json
```

Le premier script retrouve les neuf identifiants de définitions et celui de la règle à partir de **votre** export. Il crée `local/ibm-run.json` et `local/prepared/07_native_business_report.sql`. Si l’export contient plusieurs exécutions, ajouter `--run-id VOTRE_ID_EXECUTION` à la préparation.

Le rapprochement doit retourner `exact_match: true`, **55 violations** et **48 clients concernés**, sans différence sur les populations ni les lignes en écart des vingt exigences.

Exécuter ensuite `local/prepared/07_native_business_report.sql` dans Db2. La vue générée associe définition et colonne liée à l’exigence métier, conserve les valeurs historiques et déduplique les deux colonnes de la condition. Elle ne dépend pas des valeurs de Disambiguator de la démonstration d’origine. Consulter le détail des anomalies et les totaux par exécution.

## 10. Corriger et relancer le même job

Après conservation de l’export initial, exécuter `local/prepared/05_correct_clients.sql`, puis `local/prepared/10_corrected_reference_validation.sql` dans un nouvel éditeur Db2.

Les 47 modifications sont des corrections synthétiques documentées dans [data/corrections.json](data/corrections.json). Le rapport SQL de référence doit retrouver les 200 clients et zéro violation pour chaque exigence.

Depuis la règle native déjà sauvegardée, cliquer **Run rule**. Ne pas recréer la règle ou modifier les exigences. Attendre une nouvelle exécution : **200 clients testés, 200 conformes, zéro en écart**.

## 11. Vérifier la nouvelle exécution et l’historique

Télécharger l’export complet dans `local/verification.csv`. La table en ajout peut contenir les deux exécutions. Retrouver leurs identifiants si nécessaire :

```sh
python3 -c 'import csv; print(*sorted({r["Job_run_ID"] for r in csv.DictReader(open("local/verification.csv", encoding="utf-8-sig", newline=""))}), sep="\n")'
```

Puis sélectionner l’identifiant de la **nouvelle** exécution :

```sh
python3 scripts/verify_native_output.py local/verification.csv \
  --state corrected --run-id VOTRE_NOUVEL_ID_EXECUTION \
  --report local/verification-reconciliation.json
```

Le rapport doit retourner `exact_match: true` et zéro violation. Relancer les SELECT de `07_native_business_report.sql` pour comparer les deux exécutions. Les écarts initiaux doivent rester associés à l’ancienne exécution et à leurs anciennes valeurs, même après modification de la table source.

| Mesure de référence | Initial | Après correction |
|---|---:|---:|
| Clients testés | 200 | 200 |
| Violations règle/client | 55 | 0 |
| Clients distincts concernés | 48 | 0 |
| Lignes brutes d’audit | 3 888 | 3 900 |
| Différences avec la référence indépendante | 0 | 0 |

La référence conserve 7 788 lignes d’audit. Le nombre de lignes brutes n’est pas un nombre de violations : l’audit est produit par définition, colonne liée et client évalué. Si une configuration ou une version produit change la forme de l’export, examiner cette différence avant d’accepter la reproduction.

Les services et l’audit restent dans votre compte. Les fichiers de `local/` ne sont pas versionnés ; conserver les exports nécessaires à votre propre démonstration.
