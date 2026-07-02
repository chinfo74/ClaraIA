<?php
/**
 * Intégration du widget Clara dans un template Zend / PHP.
 *
 * Préparation (une seule fois) :
 *   1. Copiez `clara-widget.js` dans les assets du site, ex. /public/assets/js/clara-widget.js
 *   2. Côté backend Clara (FastAPI), ajoutez le domaine du site dans ALLOWED_ORIGINS (.env)
 *      pour autoriser les appels CORS depuis location-cure.net.
 *
 * Puis collez le bloc ci-dessous juste avant la balise </body> de votre layout.
 */

// URL publique du backend Clara (FastAPI). À adapter selon votre déploiement.
$claraApiUrl = 'https://api.voyagedo.fr';
?>

<!-- ── Widget Clara — assistante virtuelle ────────────────────────────────── -->
<div id="clara-widget"></div>
<script
  src="/assets/js/clara-widget.js"
  data-api-url="<?= htmlspecialchars($claraApiUrl, ENT_QUOTES) ?>"
  data-logo="/assets/img/logo.png"
  data-title="Clara"
  data-subtitle="Assistante Voyage d'Ô"
  defer></script>
<!-- ───────────────────────────────────────────────────────────────────────── -->
