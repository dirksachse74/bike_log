<p><?= h(t('These wheels sit directly on {bike}. Put them into a wheelset when you swap whole wheel pairs between bikes: the wheelset then counts km of its own, and the wheels with their tires, tubes and cassette carry on with theirs.', ['bike' => $bike['name']])) ?></p>
<?php if (!$wheels): ?><p class="muted"><?= h(t('No wheels are fitted directly on this bike.')) ?></p>
<?php else: ?>
<ul><?php foreach ($wheels as $w): ?><li><a href="<?= h(url('part', ['id' => $w['id']])) ?>"><?= h(Domain::componentName($w)) ?></a> <span class="muted">(<?= h(Catalog::slotName($w['slot'])) ?><?= h(t(', since {date}', ['date' => $w['installed_on']])) ?>)</span></li><?php endforeach; ?></ul>
<form method="post" class="card" action="<?= h(url('group_wheels', ['bike' => $bike['id']])) ?>">
  <?= Csrf::field() ?>
  <?php if ($choices): ?><label><?= h(t('Wheelset')) ?><select name="wheelset_id"><?= options(array_column(array_map(fn($w) => ['id' => $w['id'], 'n' => Domain::componentName($w)], $choices), 'n', 'id'), '', true, t('A new wheelset')) ?></select></label><?php endif; ?>
  <?= field('label', t('Name of the new wheelset'), '', 'text', ['maxlength' => 160, 'placeholder' => t('Wheelset ({bike})', ['bike' => $bike['name']])]) ?>
  <?= field('on', t('From'), today(), 'date', ['required' => true]) ?>
  <button class="btn primary"><?= h(t('Put them into a wheelset')) ?></button>
  <a class="btn" href="<?= h(url('bike', ['id' => $bike['id']])) ?>"><?= h(t('Cancel')) ?></a>
</form>
<?php endif; ?>
