package com.androiduse.fixture;

import android.app.Activity;
import android.os.Bundle;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

/** No network, storage or account permissions; all state is ephemeral. */
public final class MainActivity extends Activity {
    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(24, 80, 24, 80);
        TextView title = new TextView(this);
        title.setText("Android Use Fixture");
        title.setTextSize(22);
        root.addView(title);
        final EditText input = new EditText(this);
        input.setId(R.id.input);
        input.setSingleLine(true);
        input.setHint("Type here");
        input.setContentDescription("Fixture input");
        root.addView(input);
        final TextView status = new TextView(this);
        status.setId(R.id.status);
        status.setText("Ready");
        status.setTextSize(20);
        root.addView(status);
        Button apply = new Button(this);
        apply.setId(R.id.apply);
        apply.setAllCaps(false);
        apply.setText("Apply");
        apply.setOnClickListener(new View.OnClickListener() {
            @Override public void onClick(View view) {
                status.setText("Applied: " + input.getText().toString());
            }
        });
        root.addView(apply);
        for (final int id : new int[] {R.id.first, R.id.second}) {
            Button duplicate = new Button(this);
            duplicate.setId(id);
            duplicate.setAllCaps(false);
            duplicate.setText("Duplicate");
            duplicate.setOnClickListener(new View.OnClickListener() {
                @Override public void onClick(View view) {
                    status.setText(id == R.id.first ? "First" : "Second");
                }
            });
            root.addView(duplicate);
        }
        ScrollView scroll = new ScrollView(this);
        scroll.setId(R.id.scroll);
        LinearLayout rows = new LinearLayout(this);
        rows.setOrientation(LinearLayout.VERTICAL);
        for (int i = 1; i <= 40; i++) {
            TextView row = new TextView(this);
            row.setText("Row " + i);
            row.setTextSize(20);
            row.setPadding(12, 24, 12, 24);
            rows.addView(row);
        }
        scroll.addView(rows);
        root.addView(scroll, new LinearLayout.LayoutParams(-1, 0, 1));
        setContentView(root);
    }
}
