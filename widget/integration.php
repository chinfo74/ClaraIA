<?php
$claraApiUrl = 'https://api.voyagedo.fr';
?>

<div id="clara-widget"></div>
<script
  src="/assets/js/clara-widget.js"
  data-api-url="<?= htmlspecialchars($claraApiUrl, ENT_QUOTES) ?>"
  data-logo="/assets/img/logo.png"
  data-title="Clara"
  data-subtitle="Assistante Voyage d'Ô"
  defer></script>
