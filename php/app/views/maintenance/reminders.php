<p class="muted"><?= h(t('Every reminder shows how it is counted. A reminder helps you plan; it never means a part is safe.')) ?></p>
<?= View::partial('partials/reminders', ['reminders' => $reminders, 'back' => 'reminders']) ?>
