<p>These wheels sit directly on <?= h($bike['name']) ?>. Put them into a wheelset when you swap whole wheel pairs between bikes:
  the wheelset then counts km of its own, and the wheels with their tires, tubes and cassette carry on with theirs.</p>
<?php if (!$wheels): ?><p class="muted">No wheels are fitted directly on this bike.</p>
<?php else: ?>
<ul><?php foreach ($wheels as $w): ?><li><a href="<?= h(url('part', ['id' => $w['id']])) ?>"><?= h(Domain::componentName($w)) ?></a> <span class="muted">(<?= h(Catalog::slotName($w['slot'])) ?>, since <?= h($w['installed_on']) ?>)</span></li><?php endforeach; ?></ul>
<form method="post" class="card" action="<?= h(url('group_wheels', ['bike' => $bike['id']])) ?>">
  <?= Csrf::field() ?>
  <?php if ($choices): ?><label>Wheelset<select name="wheelset_id"><?= options(array_column(array_map(fn($w) => ['id' => $w['id'], 'n' => Domain::componentName($w)], $choices), 'n', 'id'), '', true, 'A new wheelset') ?></select></label><?php endif; ?>
  <?= field('label', 'Name of the new wheelset', '', 'text', ['maxlength' => 160, 'placeholder' => 'Wheelset (' . $bike['name'] . ')']) ?>
  <?= field('on', 'From', today(), 'date', ['required' => true]) ?>
  <button class="btn primary">Put them into a wheelset</button>
  <a class="btn" href="<?= h(url('bike', ['id' => $bike['id']])) ?>">Cancel</a>
</form>
<?php endif; ?>
