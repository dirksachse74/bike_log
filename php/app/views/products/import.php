<p class="muted"><?= h(t('Import products (maker, model, specs) and optionally spares you own from JSON files, for example written by a script that reads product pages. The files are checked first; a file with any error is not imported at all. Importing the same file again changes nothing.')) ?></p>

<?php if ($results): ?>
<section><h2><?= h($done ? t('Result') : t('Check')) ?></h2>
  <?php $tokens = []; foreach ($results as $r): $rep = $r['report']; if (!empty($r['token'])) { $tokens[] = $r['token']; } ?>
  <div class="card">
    <p><strong><?= h($r['name']) ?></strong> · <?= $rep['ok'] ? status_badge('OK') : status_badge('OVERDUE') ?>
      <?php if ($rep['ok'] && $rep['counts']): $c = $rep['counts']; ?>
        <span class="muted"><?= h(t('{new} new, {updated} updated, {same} unchanged; spares: {items_new} new, {items_old} exist already', ['new' => (int)$c['CREATED'], 'updated' => (int)$c['UPDATED'], 'same' => (int)$c['UNCHANGED'], 'items_new' => (int)$c['ITEMS_CREATED'], 'items_old' => (int)$c['ITEMS_EXISTING']])) ?></span>
      <?php endif; ?></p>
    <?php if ($rep['errors']): ?><p><?= h(t('Errors (nothing from this file is imported):')) ?></p><ul class="errors"><?php foreach (array_slice($rep['errors'], 0, 200) as $e): ?><li><code><?= h($e) ?></code></li><?php endforeach; ?></ul><?php endif; ?>
    <?php if ($rep['warnings']): ?><details><summary><?= h(t('{n} warnings', ['n' => count($rep['warnings'])])) ?></summary><ul><?php foreach (array_slice($rep['warnings'], 0, 200) as $w): ?><li><code><?= h($w) ?></code></li><?php endforeach; ?></ul></details><?php endif; ?>
    <?php if ($rep['products']): ?>
    <details <?= count($rep['products']) <= 5 ? 'open' : '' ?>><summary><?= h(t('{n} products', ['n' => count($rep['products'])])) ?></summary>
      <table class="list"><?php foreach (array_slice($rep['products'], 0, 300) as $p): ?>
        <tr><td><?= !empty($p['product_id']) ? '<a href="' . h(url('product', ['id' => $p['product_id']])) . '">' . h($p['maker'] . ' ' . $p['model']) . '</a>' : h($p['maker'] . ' ' . $p['model']) ?>
          <span class="muted"><?= h(Catalog::typeName($p['component_type'])) ?></span></td>
          <td><?= h(['CREATED' => t('new'), 'UPDATED' => t('updated'), 'UNCHANGED' => t('unchanged')][$p['status']]) ?><?= $p['changed'] ? ' <span class="muted">(' . h(implode(', ', $p['changed'])) . ')</span>' : '' ?></td>
          <td class="muted"><?= h(implode(', ', array_map(fn($i) => $i['label'] . ($i['status'] === 'EXISTS' ? t(' (exists)') : t(' (new spare)')), $p['items']))) ?></td></tr>
      <?php endforeach; ?></table>
    </details>
    <?php endif; ?>
  </div>
  <?php endforeach; ?>
  <?php if (!$done && $tokens): ?>
  <form method="post" action="<?= h(url('product_import')) ?>"><?= Csrf::field() ?><input type="hidden" name="do" value="import">
    <?php foreach ($tokens as $t): ?><input type="hidden" name="token[]" value="<?= h($t) ?>"><?php endforeach; ?>
    <button class="btn primary"><?= h(tn('Import {n} file without errors', 'Import {n} files without errors', count($tokens))) ?></button>
  </form>
  <?php endif; ?>
</section>
<?php endif; ?>

<section><h2><?= h($results ? t('Check other files') : t('Choose files')) ?></h2>
  <form method="post" action="<?= h(url('product_import')) ?>" enctype="multipart/form-data" class="card"><?= Csrf::field() ?><input type="hidden" name="do" value="check">
    <label><?= h(t('JSON files (up to 50, 5 MB each)')) ?><input type="file" name="files[]" accept=".json,application/json" multiple required></label>
    <button class="btn primary"><?= h(t('Check files')) ?></button>
  </form>
</section>

<details><summary class="btn small"><?= h(t('Templates and instructions for a script')) ?></summary>
  <p><?= h(t('Give')) ?> <a href="<?= h(url('product_template', ['kind' => 'instructions'])) ?>">AGENT_INSTRUCTIONS.md</a> <?= h(t('to a developer or an AI agent that writes the script. Per part type there is a JSON schema and an example file:')) ?></p>
  <table class="list">
    <?php foreach ($types as $cat => $list): foreach ($list as $code => $name): ?>
    <tr><td><?= h($name) ?> <span class="muted"><?= h($cat) ?></span></td>
      <td><a href="<?= h(url('product_template', ['type' => $code, 'kind' => 'example'])) ?>"><?= h(t('example')) ?></a> · <a href="<?= h(url('product_template', ['type' => $code, 'kind' => 'schema'])) ?>"><?= h(t('schema')) ?></a></td></tr>
    <?php endforeach; endforeach; ?>
  </table>
</details>
