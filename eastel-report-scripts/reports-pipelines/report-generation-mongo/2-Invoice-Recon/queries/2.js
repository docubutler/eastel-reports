/*
Query 2: Domestic MO SMS total count.

Output:
{
  service_type: "SMS",
  charge_type: "MO",
  sms_type: "On Net / Off Net",
  total: 4863
}

Equivalent PostgreSQL:

SELECT
    'SMS' AS service_type,
    'MO' AS charge_type,
    'On Net / Off Net' AS sms_type,
    COUNT(*) AS total
FROM iot_portal_tb_usage_log t
WHERE t.usage_start_time >= '2026-04-01'
  AND t.usage_start_time < '2026-05-01'
  AND t.rat_type = 'SM'
  AND t.roaming_destination_id = 87
  AND t.act_usage_unit > 0;
*/

db.usage_logs.aggregate([
  {
    $group: {
      _id: null,
      total: {
        $sum: {
          $cond: [
            {
              $and: [
                { $gte: ["$usage_start_time", ISODate("{{start_date}}")] },
                { $lt: ["$usage_start_time", ISODate("{{end_date}}")] },
                { $eq: ["$rat_type", "SM"] },
                { $eq: ["$roaming_destination_id", 87] },
                { $gt: ["$act_usage_unit", 0] }
              ]
            },
            1,
            0
          ]
        }
      }
    }
  },
  {
    $project: {
      _id: 0,
      service_type: { $literal: "SMS" },
      charge_type: { $literal: "MO" },
      sms_type: { $literal: "On Net / Off Net" },
      total: 1
    }
  }
]);
