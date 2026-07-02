# API Endpoints — Voyage d'O pour Curiste

Base URL : `https://www.location-cure.net/mob1`  
Version app courante : `2.1.1`

---

## Endpoints dynamiques

| Méthode | URL complète | Fonction Flutter | Description |
|---|---|---|---|
| `GET` | `https://www.location-cure.net/mob1/urlnote` | `getAppNoteUrl()` | Récupère l'URL de l'app sur le store (Android/iOS) |
| `GET` | `https://www.location-cure.net/mob1/start` | `fetchStart()` | Données initiales au démarrage (villes, équipements…) |
| `GET` | `https://www.location-cure.net/mob1/homelist/vers/{version}` | `fetchHomeList()` | Liste des éléments de la page d'accueil |
| `GET` | `https://www.location-cure.net/mob1/checkvers/vers/{version}` | `checkVersion()` | Vérification de la version de l'application |
| `GET` | `https://www.location-cure.net/mob1/stationcard/{stationId}` | `fetchStationCard()` | Fiche détaillée d'une station thermale |
| `GET` | `https://www.location-cure.net/mob1/curecard/{cureId}` | `fetchCureCard()` | Fiche détaillée d'une cure |
| `GET` | `https://www.location-cure.net/mob1/recuppathologies/{ville}/{patho}` | `fetchCureList()` | Liste des cures filtrées par ville et pathologie |
| `GET` | `https://www.location-cure.net/mob1/recupstation` | `fetchStations()` | Liste de toutes les stations thermales |
| `GET` | `https://www.location-cure.net/mob1/recupmap` | `fetchMapData()` | Données géolocalisées pour la carte |
| `GET` | `https://www.location-cure.net/mob1/doubleorient` | `fetchDoubleOrient()` | Données écran double orientation |
| `GET` | `https://www.location-cure.net/mob1/getlogcard/id/{id}` | `fetchLogementCard()` | Fiche détaillée d'un logement |
| `GET` | `https://www.location-cure.net/mob1/getadvertbyequip/ville/{ville}/equip/{equip}/start/{start}/end/{end}` | `fetchLogementList()` | Liste des logements filtrés (ville, équipements, dates) |
| `POST` | `https://www.location-cure.net/mob1/docpost/` | `submitDocumentation()` | Envoi d'une demande de documentation |
| `GET` | `https://www.location-cure.net/mob1/addtoken/token/{token}` | `registerPushToken()` | Enregistrement du token push notifications |
| `GET` | `https://www.location-cure.net/mob1/available/{advertId}/{start}/{end}/{persons}` | `checkAvailability()` | Vérification de disponibilité d'un logement |
| `GET` | `https://www.location-cure.net/mob1/reserver/advert_id/{advertId}/start/{start}/end/{end}/adulte/{adults}/enfant/{children}` | `makeReservation()` | Effectuer une réservation de logement |

---

## URLs statiques

| URL | Utilisation |
|---|---|
| `https://www.location-cure.net/conditions-generales-application-curistes` | Page des conditions générales |
| `https://www.location-cure.net/gallery/logementphoto` | Base URL pour les photos de logements |

---

## Paramètres de chemin

| Paramètre | Type | Description |
|---|---|---|
| `{version}` | `String` | Version de l'app (ex: `2.1.1`) |
| `{stationId}` | `int` | ID de la station thermale |
| `{cureId}` | `int` | ID de la cure |
| `{ville}` | `String` | Identifiant de la ville |
| `{patho}` | `String` | Identifiant de la pathologie |
| `{id}` | `int` | ID du logement |
| `{equip}` | `String` | Identifiants des équipements |
| `{start}` | `String` | Date de début (format API) |
| `{end}` | `String` | Date de fin (format API) |
| `{persons}` | `int` | Nombre de personnes |
| `{advertId}` | `int` | ID de l'annonce (logement) |
| `{adults}` | `int` | Nombre d'adultes |
| `{children}` | `int` | Nombre d'enfants |
| `{token}` | `String` | Token push notification FCM |
